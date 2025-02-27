from dataclasses import dataclass
from pathlib import Path
from typing import List

import pytest
import re
import subprocess

from ofrak import OFRAKContext
from ofrak.core.architecture import ProgramAttributes
from ofrak_type.architecture import (
    InstructionSet,
    SubInstructionSet,
    InstructionSetMode,
)
from ofrak.core.basic_block import BasicBlock
from ofrak.core.complex_block import ComplexBlock
from ofrak.core.program import Program
from ofrak.core.patch_maker.linkable_symbol import LinkableSymbolType
from ofrak.core.patch_maker.model import SourceBundle
from ofrak.core.patch_maker.modifiers import (
    FunctionReplacementModifierConfig,
    FunctionReplacementModifier,
)
from ofrak_patch_maker.toolchain.model import (
    CompilerOptimizationLevel,
    BinFileType,
    ToolchainConfig,
)
from ofrak_patch_maker.toolchain.utils import get_repository_config
from ofrak_patch_maker.toolchain.version import ToolchainVersion
from ofrak_type.bit_width import BitWidth
from ofrak_type.endianness import Endianness

PATCH_DIRECTORY = str(Path(__file__).parent / "assets" / "src")
X86_64_PROGRAM_PATH = str(Path(__file__).parent / "assets" / "hello.out")
ARM32_PROGRAM_PATH = str(Path(__file__).parent / "assets" / "simple_arm_gcc.o.elf")


def normalize_assembly(assembly_str: str) -> str:
    """
    Normalize an assembly string:
    - strip leading and trailing whitespace from all lines
    - replace all consecutive strings of whitespace (including tabs) with a single space
    """
    assembly_lines = assembly_str.splitlines()
    assembly_lines = [line.strip() for line in assembly_lines]
    assembly_lines = [re.sub(r"\s+", " ", line) for line in assembly_lines]
    return "\n".join(assembly_lines)


@dataclass
class ProgramConfig:
    """Information on a program and the function that will be targeted."""

    path: str
    attrs: ProgramAttributes
    function_name: str
    function_vaddr: int
    function_size: int


@dataclass
class FunctionReplacementTestCaseConfig:
    """Configuration for a function replacement modification."""

    program: ProgramConfig
    # Relative filename of the source code file to use as replacement, within PATCH_DIRECTORY
    replacement_patch: str
    # Name of the section to use in the toolchain.conf file
    toolchain_name: str
    toolchain_version: ToolchainVersion
    # A list of lines that are expected to appear consecutively in the output of `objdump -d <modified program>`.
    # Note that the comparison is done after applying `normalize_assembly()` on both texts.
    expected_objdump_output: List[str]
    compiler_optimization_level: CompilerOptimizationLevel = CompilerOptimizationLevel.SPACE


X86_64_PROGRAM_CONFIG = ProgramConfig(
    X86_64_PROGRAM_PATH,
    ProgramAttributes(
        InstructionSet.X86,
        None,
        BitWidth.BIT_64,
        Endianness.LITTLE_ENDIAN,
        None,
    ),
    "main",
    0x4004C4,
    28,
)

ARM32_PROGRAM_CONFIG = ProgramConfig(
    ARM32_PROGRAM_PATH,
    ProgramAttributes(
        InstructionSet.ARM,
        SubInstructionSet.ARMv5T,
        BitWidth.BIT_32,
        Endianness.LITTLE_ENDIAN,
        None,
    ),
    "main",
    0x8068,
    40,
)

TEST_CASE_CONFIGS = [
    FunctionReplacementTestCaseConfig(
        X86_64_PROGRAM_CONFIG,
        "patch_basic.c",
        "GNU_X86_64_LINUX",
        ToolchainVersion.GNU_X86_64_LINUX_EABI_10_3_0,
        [
            "00000000004004c4 <main>:",
            "  4004c4: b8 03 00 00 00        mov    $0x3,%eax",
            "  4004c9: c3                    retq",
        ],
    ),
    FunctionReplacementTestCaseConfig(
        X86_64_PROGRAM_CONFIG,
        "patch_basic.c",
        "LLVM_12_0_1",
        ToolchainVersion.LLVM_12_0_1,
        [
            "00000000004004c4 <main>:",
            "  4004c4: 6a 03                         pushq $3",
            "  4004c6: 58                            popq %rax",
        ],
    ),
    FunctionReplacementTestCaseConfig(
        ARM32_PROGRAM_CONFIG,
        "patch_basic.c",
        "GNU_ARM_NONE",
        ToolchainVersion.GNU_ARM_NONE_EABI_10_2_1,
        [
            "00008068 <main>:",
            "    8068: e3a00003  mov r0, #3",
            "    806c: e12fff1e  bx lr",
        ],
    ),
    FunctionReplacementTestCaseConfig(
        X86_64_PROGRAM_CONFIG,
        "patch_two_functions.c",
        "GNU_X86_64_LINUX",
        ToolchainVersion.GNU_X86_64_LINUX_EABI_10_3_0,
        [
            "00000000004004c4 <main>:",
            "  4004c4: 55                    push   %rbp",
            "  4004c5: 48 89 e5              mov    %rsp,%rbp",
            "  4004c8: b8 00 00 00 00        mov    $0x0,%eax",
            "  4004cd: e8 02 00 00 00        callq  4004d4 <main+0x10>",
            "  4004d2: 5d                    pop    %rbp",
            "  4004d3: c3                    retq   ",
            "  4004d4: 55                    push   %rbp",
            "  4004d5: 48 89 e5              mov    %rsp,%rbp",
            "  4004d8: b8 04 00 00 00        mov    $0x4,%eax",
            "  4004dd: 5d                    pop    %rbp",
            "  4004de: c3                    retq   ",
        ],
        CompilerOptimizationLevel.NONE,
    ),
]


@pytest.mark.parametrize("config", TEST_CASE_CONFIGS)
async def test_function_replacement_modifier(ofrak_context: OFRAKContext, config):
    root_resource = await ofrak_context.create_root_resource_from_file(config.program.path)
    await root_resource.unpack_recursively()
    target_program = await root_resource.view_as(Program)

    source_bundle_r = await target_program.resource.create_child(data=b"", tags=(SourceBundle,))
    source_bundle = await source_bundle_r.view_as(SourceBundle)
    await source_bundle.initialize_from_disk(PATCH_DIRECTORY)

    function_cb = ComplexBlock(
        virtual_address=config.program.function_vaddr,
        size=config.program.function_size,
        name=config.program.function_name,
    )

    function_cb_parent_code_region = await target_program.get_code_region_for_vaddr(
        config.program.function_vaddr
    )

    function_cb.resource = await function_cb_parent_code_region.create_child_region(function_cb)

    # Create a dummy basic block in the complex block, so its `get_mode` method won't fail.
    dummy_bb = BasicBlock(0, 0, InstructionSetMode.NONE, False, None)
    await function_cb.resource.create_child_from_view(dummy_bb)

    await target_program.define_linkable_symbols(
        {config.program.function_name: (config.program.function_vaddr, LinkableSymbolType.FUNC)}
    )

    target_program.resource.add_attributes(config.program.attrs)

    await target_program.resource.save()

    function_replacement_config = FunctionReplacementModifierConfig(
        source_bundle.resource.get_id(),
        {config.program.function_name: config.replacement_patch},
        ToolchainConfig(
            file_format=BinFileType.ELF,
            force_inlines=True,
            relocatable=False,
            no_std_lib=True,
            no_jump_tables=True,
            no_bss_section=True,
            compiler_optimization_level=config.compiler_optimization_level,
            check_overlap=False,
        ),
        config.toolchain_version,
    )

    await target_program.resource.run(FunctionReplacementModifier, function_replacement_config)
    new_program_path = f"replaced_{Path(config.program.path).name}"
    await target_program.resource.flush_to_disk(new_program_path)

    # Check that the modified program looks as expected.
    readobj_path = get_repository_config("toolchain.conf", config.toolchain_name, "BIN_PARSER")

    # LLVM-specific fix: use llvm-objdump, not llvm-readobj
    if "readobj" in readobj_path:
        readobj_path = readobj_path.replace("readobj", "objdump")

    subprocess_result = subprocess.run(
        [readobj_path, "-d", new_program_path], capture_output=True, text=True
    )
    readobj_output = subprocess_result.stdout

    expected_objdump_output_str = "\n".join(config.expected_objdump_output)

    assert normalize_assembly(expected_objdump_output_str) in normalize_assembly(readobj_output)
