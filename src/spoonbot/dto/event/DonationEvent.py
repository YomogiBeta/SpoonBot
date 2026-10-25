from pydantic import BaseModel

from spoonbot.dto.DonationBody import DonationBody
from spoonbot.dto.SpoonAuthorization import SpoonAuthorization


class GiftEvent(BaseModel, frozen=True):
    donation_body: DonationBody
    authorization: SpoonAuthorization
