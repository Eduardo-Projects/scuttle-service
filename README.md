<h1 align="center">
  <br>
  <a href="https://www.scuttle.gg"><img src="./assets/scuttle_cropped.png" alt="Scuttle" width="250"></a>
  <br>
  ScuttleService
  <br>
</h1>

<h4 align="center">A backend data fetching and caching service for <a href="https://scuttle.gg/" target="_blank">Scuttle</a>.</h4>

<p align="center">
  <a href="https://www.buymeacoffee.com/eduardoalba">
    <img src="https://img.shields.io/badge/$-donate-ff69b4.svg?maxAge=2592000&amp;style=flat">
  </a>
</p>

## Purpose

- ScuttleService serves one purpose, to regularly fetch and store league of legends match data for every summoner registered to Scuttle.
- The reason this service is necessary is due to the structure of Scuttle and the rate limits of [Riot's](https://www.riotgames.com/en) API.
  - Scuttle, a discord bot, can not run such a heavy backend process while also processing the command inputs of users.
  - ScuttleService was created to offload this process from Scuttle.
  - ScuttleService is hosted seperately from the discord bot and runs hourly on the hour.
- When summoner is first added to a guild within Scuttle, this script fetches and stores the data from their last 30 games.
  - After this initial setup, ScuttleService checks when a summoner's data has last been processed and fetches the data in between.
- This entire process powers Scuttle's database and allows for seamless and uninterrupted user experience.

## Credits

This software uses the following open source packages:

- [discord.py](https://discordpy.readthedocs.io/en/stable/)

## Support

<a href="https://www.buymeacoffee.com/eduardoalba" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/purple_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

---

> GitHub [@eduardoalba00](https://github.com/eduardoalba00) &nbsp;&middot;&nbsp;
