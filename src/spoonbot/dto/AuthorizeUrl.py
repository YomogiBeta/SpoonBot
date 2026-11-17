from dataclasses import dataclass


@dataclass
class AuthorizeUrl:
    """SpoonアカウントとのOAuth連携に使用する認可URLを保持するDTOです。

    ``SpoonBot.user_authorize_url``の戻り値として利用されます。

    Attributes:
        url: ユーザーをリダイレクトさせるOAuthの認可URL。
        state: 認可リクエスト時に生成されたstate値。コールバック時の改ざん検知に
            使用します。
    """

    url: str
    state: str
