<style>
  button {
    padding-top: 0.5em;
    padding-bottom: 0.5em;
    padding-left: 1em;
    padding-right: 1em;
  }

  button:hover,
  button:focus {
    outline: none;
    box-shadow: inset 1px 1px 0 var(--main-fg-color),
      inset -1px -1px 0 var(--main-fg-color);
  }

  button:active {
    box-shadow: inset 2px 2px 0 var(--main-fg-color),
      inset -2px -2px 0 var(--main-fg-color);
  }

  .container {
    min-height: 100%;
    display: flex;
    flex-direction: column;
    flex-wrap: nowrap;
    justify-content: center;
    align-items: stretch;
    align-content: center;
  }

  .inputs {
    flex-grow: 1;
  }

  .inputs *:first-child {
    margin-top: 0;
  }

  .actions {
    margin-top: 2em;
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    justify-content: space-evenly;
    align-items: center;
    align-content: center;
  }

  input {
    background: inherit;
    color: inherit;
    border: none;
    border-bottom: 1px solid white;
    flex-grow: 1;
    margin-left: 1ch;
  }

  input:focus {
    outline: none;
    box-shadow: inset 0 -1px 0 var(--main-fg-color);
  }

  /* Adapted from: https://moderncss.dev/pure-css-custom-checkbox-style/ */
  input[type="checkbox"] {
    flex-grow: 0;
    margin-left: 1ch;
    /*
    appearance: none;
    background-color: var(--main-bg-color);
    margin: 0;
    color: currentColor;
    width: 1em;
    height: 1em;
    border: 1px solid currentColor;
    display: grid;
    place-content: center;
    */
  }

  /*
  input[type="checkbox"]:focus {
    box-shadow: none;
  }

  input[type="checkbox"]::before {
    content: "";
    width: 0.45em;
    height: 0.45em;
    transform: scale(0);
    transition: 120ms transform ease-in-out;
    box-shadow: inset 1em 1em var(--main-fg-color);
  }

  input[type="checkbox"]:checked::before {
    transform: scale(1);
  }
  */

  label {
    margin-bottom: 1em;
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    justify-content: space-evenly;
    align-items: baseline;
    align-content: center;
    white-space: nowrap;
  }

  .row {
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    justify-content: space-evenly;
    align-items: baseline;
    align-content: center;
    white-space: nowrap;
  }

  .error {
    margin-top: 2em;
  }
</style>

<script>
  import { selected, selectedResource } from "./stores.js";

  export let modifierView;
  let toFind,
    toReplace,
    nullTerminated = true,
    allowOverflow = false,
    errorMessage;

  function refreshResource() {
    // Force hex view refresh with colors
    const originalSelected = $selected;
    $selected = undefined;
    $selected = originalSelected;
  }

  async function findAndReplace() {
    try {
      if ($selectedResource) {
        await $selectedResource.find_and_replace(
          toFind,
          toReplace,
          nullTerminated,
          allowOverflow
        );
      }

      modifierView = undefined;
      refreshResource();
    } catch (err) {
      try {
        errorMessage = JSON.parse(err.message).message;
      } catch (_) {
        errorMessage = err.message;
      }
    }
  }
</script>

<div class="container">
  <div class="inputs">
    <p>
      Replace all instances of a string with another string. Replacements occur
      in the data of the currently selected resource.
    </p>
    <label>
      String to find:
      <input type="text" bind:value="{toFind}" />
    </label>
    <label>
      String to replace:
      <input type="text" bind:value="{toReplace}" />
    </label>
    <div class="row">
      <label>
        Null terminate replacement string
        <input type="checkbox" bind:checked="{nullTerminated}" />
      </label>
      <label>
        Allow overflowing replaced string
        <input type="checkbox" bind:checked="{allowOverflow}" />
      </label>
    </div>
    {#if errorMessage}
      <p class="error">
        Error:
        {errorMessage}
      </p>
    {/if}
  </div>
  <div class="actions">
    <button on:click="{findAndReplace}">Find and Replace</button>
    <button on:click="{() => (modifierView = undefined)}">Cancel</button>
  </div>
</div>
