import { botInfromation } from "./api/spoonbot.js"

// Injection bot name
const botData = await botInfromation()
document.querySelectorAll('.bot-name').forEach(element => {
  element.textContent = botData.bot_name
});