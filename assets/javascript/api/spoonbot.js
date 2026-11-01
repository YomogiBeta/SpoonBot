
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
	const data = await result.json()
	return data.csrf_token
}