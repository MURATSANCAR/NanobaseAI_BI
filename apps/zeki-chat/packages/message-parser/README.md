<!--header-->

<p align="center">
  <a href="[upstream link removed] title="ZEKI AI CHAT">
    <img src="[upstream link removed] alt="ZEKI AI CHAT" />
  </a>
</p>

# `@rocket.chat/message-parser`

> ZEKI AI CHAT parser for messages

---

![npm@latest]([upstream link removed]) ![npm@next]([upstream link removed]) !npm downloads !License: MIT

!deps !npm bundle size

<!--/header-->

## Description

ZEKI AI CHAT grammar with the purpose of parsing the messages of the ZEKI AI CHAT, converting text to an AST tree.

The grammar provides support for markdown, mentions and emojis.

## Supported markup

- quotes
- bold/italic/strike
- ordered lists
- unordered lists
- task lists
- phone numbers
- mentions
- emoji
- colors
- URI's
- mentions users/channels
- timestamps

## Timestamps

The timestamp tag is a special tag that allows you to convert a Unix timestamp to a human-readable date and time.

Timestamps are allowed inside strike elements.

### Usage

Pattern: <t:{timestamp}:?{format}>

- {timestamp} is a Unix timestamp
- {format} is an optional parameter that can be used to customize the date and time format.

#### Formats

| Format | Description               | Example                                 |
| ------ | ------------------------- | --------------------------------------- |
| `t`    | Short time                | 12:00 AM                                |
| `T`    | Long time                 | 12:00:00 AM                             |
| `d`    | Short date                | 12/31/2020                              |
| `D`    | Long date                 | Thursday, December 31, 2020             |
| `f`    | Full date and time        | Thursday, December 31, 2020 12:00 AM    |
| `F`    | Full date and time (long) | Thursday, December 31, 2020 12:00:00 AM |
| `R`    | Relative time             | 1 year ago                              |

## Contributing

<!--contributing(msg)-->

Contributions, issues, and feature requests are welcome!<br />
Feel free to check the issues.

<!--/contributing(msg)-->

Whenever you find a grammar-related bug, start by inserting the test case.

We are open to other tags/markups, as long as they don't generate unexpected behavior.

## Observations and known issues

- Nested lists are unsupported
- `URL` rule doesn't allow whitespace, `(`, or `)`
