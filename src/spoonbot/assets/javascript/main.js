import { botInfromation, csrfToken, inviteBot } from "./api/spoonbot.js"

// Injection bot name
const botData = await botInfromation()
document.querySelectorAll('.bot-name').forEach(element => {
  element.textContent = botData.bot_name
});

// Invite bot in usert live room
const inviteButton = document.querySelector('#invite-button')
const inviteBotHandler= async () => {
  const token = await csrfToken()
  const result = await inviteBot(token)
  if (!result) {
    inviteButton.textContent = "既に入室を試みています。"
    return
  }
  inviteButton.textContent = "招待に成功しました"
}
inviteButton.addEventListener("click", inviteBotHandler)


const operationPageLink = document.querySelector('#bot-operation-page')
if (botData.page != null) {
  operationPageLink.classList.toggle("hidden")
  operationPageLink.setAttribute('href', botData.page);
}