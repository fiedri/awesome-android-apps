# Contributing Guidelines

This document shows you how to get started with your contribution to this project. If you follow these, your PR will be merged quickly.

[**ADDING A NEW APP**](#adding-a-new-app "ADDING A NEW APP")

[**OTHER CONTRIBUTIONS**](#other-contributions "OTHER CONTRIBUTIONS")

## Adding a new app

- Fork the repo

  - <https://github.com/albertomosconi/foss-apps/fork>

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

  - Once the app is added, run `build.py` to regenerate the markdown content:
    ```
    $ python scripts/build.py
    ```
    This rebuilds the category tables in `categories/` from the `apps/*.json` files, and updates the README app counter and table of contents.

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

## Other Contributions

There are no specific rules for any other type of contribution, feel free to send your PR!
