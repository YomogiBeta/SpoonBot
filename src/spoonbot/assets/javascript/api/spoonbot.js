
export const botInfromation = async () => {
	const result = await fetch("/api/v1/bot")
	if (!result.ok) {
		throw new Error("Failed: Get spoon infromation")
	}
	/** @type {import("../types/types.js").Bot} Bot */
	const data = await result.json()
	return data
}

export const csrfToken = async () => {
	const result = await fetch("/api/v1/csrf-token")
	if (result.status == 401) {
		return null
	}
	if (!result.ok) {
		throw new Error("Failed: Get spoon infromation")
	}
	/** @type {import("../types/types.js").CsrfToken} CsrfToken */
	const data = await result.json()
	return data.csrf_token
}

export const inviteBot = async (token) => {
	const result = await fetch("/api/v1/bot/invite", {
		method: "POST", headers: {"X-CSRF-TOKEN": token}
	})
	if (result.status == 409) {
		return false
	}
	if (!result.ok) {
		throw new Error("Failed: Invite bot")
	}
	return true
}