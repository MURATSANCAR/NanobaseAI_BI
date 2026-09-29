# ZEKI AI CHAT.Livechat
![Language grade: JavaScript]([upstream link removed])
![Total alerts]([upstream link removed])
[![Storybook](https://cdn.jsdelivr.net/gh/storybooks/brand@master/badge/badge-storybook.svg)]([upstream link removed])

Currently, it's very common to find chat pop-ups when you're browsing websites.

Those widgets, at ZEKI AI CHAT, are called **LiveChat**.

**LiveChat** is a small and lightweight application designed to provide B2C (Business-to-customer) communication between Agents and website visitors and is developed with [Preact](https://preactjs.com).

## Running a development environment

With your **ZEKI AI CHAT** running locally at http://localhost:3000
<br />

1. Install all node dependencies.
``` bash
yarn
```

2. Build preact application to `/build` folder
``` bash
yarn dev
```

3. In another terminal, run webpack with hot reload at http://localhost:8080
``` bash
yarn start
```

4. Open this file below in your browser
``` bash
widget-demo.html
```

*OBS: For a better performance, you can run this `widget-demo.html` on a [http server](https://github.com/http-party/http-server).*

## Different host

To select a different host on your local widget, check this configuration at `/src/api.js` file.

``` javascript
const host = window.SERVER_URL
	|| queryString.parse(window.location.search).serverUrl
	|| (process.env.NODE_ENV === 'development' ? 'http://localhost:3000' : null);
```

Here, you can change to your new configuration.

``` javascript
const host = window.SERVER_URL
	|| queryString.parse(window.location.search).serverUrl
	|| (process.env.NODE_ENV === 'development' ? 'https://your.rocketserver.com' : null);
```

## Available CLI Commands

``` bash
# install dependencies
yarn

# serve with hot reload at localhost:8080
yarn start

# build preact application to "build" folder
yarn dev

# build for production with minification
yarn build

# test the production build locally
yarn serve

# run tests with jest and preact-render-spy
yarn test

# run the storybook
yarn storybook
```

## Screens:
![image](https://user-images.githubusercontent.com/5263975/44279585-497b2980-a228-11e8-81a2-36bc3389549e.png)
![image](https://user-images.githubusercontent.com/5263975/44279599-5730af00-a228-11e8-8873-553ef53ee25a.png)
![image](https://user-images.githubusercontent.com/5263975/44279626-6f083300-a228-11e8-8886-c430b28a8e75.png)
![image](https://user-images.githubusercontent.com/5263975/44279634-74657d80-a228-11e8-9583-bf8079972696.png)
![image](https://user-images.githubusercontent.com/5263975/44279639-7b8c8b80-a228-11e8-9815-1a0e3540c4f5.png)
![image](https://user-images.githubusercontent.com/5263975/44279643-847d5d00-a228-11e8-804e-27b973dee8b2.png)
![image](https://user-images.githubusercontent.com/5263975/44279655-90691f00-a228-11e8-8511-4a328a77e5bb.png)
