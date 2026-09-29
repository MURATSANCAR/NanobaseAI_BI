<!--header-->

<p align="center">
  <a href="[upstream link removed] title="ZEKI AI CHAT">
    <img src="[upstream link removed] alt="ZEKI AI CHAT" />
  </a>
</p>

# `@rocket.chat/fuselage-ui-kit`

> UiKit elements for ZEKI AI CHAT Apps built under Fuselage design system

---

![npm@latest]([upstream link removed]) ![npm@next]([upstream link removed]) !react version [![Storybook](https://cdn.jsdelivr.net/gh/storybookjs/brand@master/badge/badge-storybook.svg)]([upstream link removed]) !npm downloads !License: MIT

!deps !peer deps !dev deps !npm bundle size

<!--/header-->

## Install

<!--install-->

Firstly, install the peer dependencies (prerequisites):

```sh
npm i @rocket.chat/fuselage @rocket.chat/fuselage-hooks @rocket.chat/icons @rocket.chat/styled react react-dom

# or, if you are using yarn:

yarn add @rocket.chat/fuselage @rocket.chat/fuselage-hooks @rocket.chat/icons @rocket.chat/styled react react-dom
```

Add `@rocket.chat/fuselage-ui-kit` as a dependency:

```sh
npm i @rocket.chat/fuselage-ui-kit

# or, if you are using yarn:

yarn add @rocket.chat/fuselage-ui-kit
```

<!--/install-->

## Contributing

<!--contributing(msg)-->

Contributions, issues, and feature requests are welcome!<br />
Feel free to check the issues.

<!--/contributing(msg)-->

### Building

As this package dependends on others in this monorepo, before anything run the following at the root directory:

<!--yarn(build)-->

```sh
yarn build
```

<!--/yarn(build)-->

### Linting

To ensure the source is matching our coding style, we perform [linting](<https://en.wikipedia.org/wiki/Lint_(software)>).
Before commiting, check if your code fits our style by running:

<!--yarn(lint)-->

```sh
yarn lint
```

<!--/yarn(lint)-->

Some linter warnings and errors can be automatically fixed:

<!--yarn(lint-and-fix)-->

```sh
yarn lint-and-fix
```

<!--/yarn(lint-and-fix)-->

### Component stories

We develop and describe our visual components in the form of stories, manage by a tool called [Storybook](https://storybook.js.org/).
To start developing with Storybook, run:

<!--yarn(storybook)-->

```sh
yarn storybook
```

<!--/yarn(storybook)-->
