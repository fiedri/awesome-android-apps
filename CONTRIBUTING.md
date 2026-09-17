# Contributing Guidelines

This document shows you how to get started with your contribution to this project. If you follow these, your PR will be merged quickly.

[**ADDING A NEW APP**](#adding-a-new-app "ADDING A NEW APP")

[**REMOVING AN APP**](#removing-an-app "REMOVING AN APP")

[**OTHER CONTRIBUTIONS**](#other-contributions "OTHER CONTRIBUTIONS")

## Adding a new app

There are two ways to add a new app:

1. **Open an issue**: If you just want to suggest an app without dealing with the repo, [open an issue](https://github.com/fiedri/awesome-mobile-apps/issues/new?template=app-suggestion.md) with the app details and we'll take care of it.
2. **Submit a PR**: If you want to contribute directly, follow the steps below.

### Submit a PR

- Fork the repo

  - <https://github.com/fiedri/awesome-android-apps>

- Check out a new branch from `main` and name it the same as the app you want to add:

  - Run this command in a terminal (replacing `APP_NAME` with the name of your app)
    ```
    $ git checkout -b APP_NAME
    ```
    If you get an error, you may need to run this command first
    ```
    $ git remote update && git fetch
    ```
  - Use one branch per app

- Add your app to the list with the helper scripts, no need to edit the json by hand

  - Run `add.py` from the repo root and answer the questions it asks:
    ```
    $ python scripts/add.py
    ```
    It will first ask if you want to add a **new app** (`0`) or a **new category** (`1`). For a new app it will walk you through the required fields (name, source and description) and the optional ones (fdroid, playstore and website), validating every link before saving. The app is added to the `apps/*.json` file, automatically placed in the correct category and in alphabetical order.

  - Want to know more before running? The [scripts README](scripts/README.md) explains the setup (virtual environment, dependencies and the optional GitHub token) plus every helper script.

  - Once the app is added, run `build.py` to regenerate the markdown content:
    ```
    $ python scripts/build.py
    ```
    This regenerates `ALL_APPS.md` (a single file with every category table) from the `apps/*.json` files, and updates the README app counter, table of contents and status legend.

  - <details><summary>Fields stored per app (reference, in case you ever edit the json by hand)</summary>

    ```
      {
            "host": "",
            "name": "",
            "description": "",
            "stars_link": "",
            "source": "",
            "fdroid": "",
            "playstore": "",
            "website": ""
      }
    ```

    `host` should either be "GitHub" or "GitLab", if your app isn't provided through one of these platforms please delete this field, along with the `stars_link` field. The latter should contain the link for the stars badge using the following templates:

    - GitHub: `https://img.shields.io/github/stars/<USERNAME>/<REPO>.svg?label=★&style=flat`
    - GitLab: please refer to [**issue #1**](https://github.com/albertomosconi/foss-apps/issues/1 "issue #1").

    `description` should contain a text from 15 to 60 words, describing the key functionality and selling points of your application.

    </details>

- Commit your changes

  - Make sure your commit message follows the following pattern, where `APP_NAME` is the name of your app, and `CATEGORY_NAME` is the category in which your app resides
    ```
    $ git commit -am "app: add APP_NAME in CATEGORY_NAME"
    ```

- Push to the branch

  - Check that you're pushing to the branch named after your app
    ```
    $ git push origin APP_NAME
    ```

- Make a pull request

  - Make sure you send the PR to the `main` branch

- Don't forget to star the repo ;)

### Open an issue

If you prefer, you can simply [open an issue](https://github.com/fiedri/awesome-mobile-apps/issues/new?template=app-suggestion.md) with the following information:

- **App name**
- **Source link** (GitHub/GitLab repo)
- **Short description** (15-60 words)
- **Play Store / F-Droid links** (optional)
- **Website** (optional)

We'll review it and add it to the list.

## Removing an app

Apps whose repository, store pages or maintainers are gone are regularly flagged by
`scripts/curate.py` (see the [scripts README](scripts/README.md)), but you can also remove an app by
hand when you know it is no longer maintained or cannot be obtained anywhere.

The data lives in three separate layers, so a manual removal touches two places:

1. **Remove the app entry** from its `apps/*.json` file (identity only — delete the whole `{ ... },` block).
2. **Purge the stale facts** so the app does not linger in the cache or overrides:
   ```
   $ python scripts/curate.py remove --dir apps
   ```
   The `remove` command deletes any cache/overrides entry whose app no longer exists in the `apps/*.json` files, cleans dead store links from other apps and logs the removal to `REMOVED.md`.
3. **Regenerate the markdown tables**:
   ```
   $ python scripts/build.py
   ```

No need to run `check` — it only refreshes the cache from the network, it never removes anything.

Before sending a PR to remove an app, make sure the **source repository no longer exists,
is archived AND inactive, or ships no releases AND every store returns a real 404**.
An app is kept if any store still works, the repo still publishes releases, or a human
pinned its status. When in doubt, mention why you think it should go in the PR description.

## Other Contributions

There are no specific rules for any other type of contribution, feel free to send your PR!
