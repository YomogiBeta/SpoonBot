# Spoonbot

Spoonbotは、オーディオライブプラットフォーム「Spoon」が公開している、Bot機能の提供API「[Spoon Developpers](https://developers.spooncast.net/docs/ja)」を非常に簡単に利用できるようにするラッパーライブラリです。

主な特徴は以下の通りです。

- **周辺処理不要**: Oauth認可、トークン管理、エラーハンドリング、再接続などSpoon Developpersを利用するために本来必要な様々な周辺処理を実装せずに済みます。
- **直感的**: PythonでBot開発を行うときによく見られる直感的な書き方でSpoonのBotを開発できます。
- **簡単**: 少ない記述で実装可能。水平スケールしないのであれば、内臓のSQLite3ですぐに動作します。(MySQLも利用可)
- **型安全**: Spoon Developpersからの応答はPydanticによって検証され、エディタ補完の効くデータとして受け取ることができます。

## Spoon Developpersの申請

本ライブラリの使用するためには、以下の申請が完了している必要があります。
<https://developers.spooncast.net/docs/ja/getting-started/app-registration>

## インストール

```bash
pip install spoonbot
```

uvを利用するのであれば、

```bash
uv add spoonbot
```

## Example

以下の内容で`main.py`を作成します。

```python
from spoonbot import (
    ChatEvent,
    SpoonBot,
    SpoonPermission,
)

spoonbot = SpoonBot(
    permissions=set(SpoonPermission)
)


@spoonbot.chat_event
async def hello(chat_event: ChatEvent):
    if chat_event.chat_body.message == "Hello":
        await spoonbot.send_chat(
            f"Hello world {chat_event.chat_body.user.nickname}!!",
            chat_event.authorization,
        )

spoonbot.start()
```

<details markdown="1">
<summary>他にも、様々なイベントを受け取れます</summary>

```Python
@spoonbot.connect_event
async def first_message(connect_event: ConnectEvent):
    if not connect_event.reconnect:
        await spoonbot.send_chat(
            "I’m here!",
            connect_event.authorization,
        )

@spoonbot.like_event
async def like(like_event: LikeEvent):
    await spoonbot.send_chat(
        f"Thankyou Heart!! {like_event.like_body.user.nickname}!!",
        like_event.authorization,
    )


@spoonbot.join_event
async def join(join_event: JoinEvent):
    await spoonbot.send_chat(
        f"Welcome {join_event.presence_body.user.nickname}!!",
        join_event.authorization,
    )


@spoonbot.gift_event
async def gift(gift_event: GiftEvent):
    await spoonbot.send_chat(
        f"Thankyou gift! {gift_event.donation_body.user.nickname}!!",
        gift_event.authorization,
    )


@spoonbot.follow_event
async def follow(follow_event: FollowEvent):
    await spoonbot.send_chat(
        f"Thankyou follow! {follow_event.follow_body.user.nickname}!!",
        follow_event.authorization,
    )


@spoonbot.end_event
async def end(end_event: EndEvent):
    print(f"bye {end_event.authorization.id}")
```

</details>

## 必要な環境変数

必須の物は必ず指定する必要があります。ただし、環境変数キーまたはSpoonBot初期荷時引数のどちらかで指定すればよいです。

| 環境変数キー             | SpoonBot初期化時引数 | 説明                                                                                                                                                                                                                                                                                                         | 必須 | 
| ------------------------ | -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---- | 
| SPOON_CLIENT_ID          | spoon_client_id      | Spoon Developpersのコンソールページで発行したClient id。                                                                                                                                                                                                                                                     | ✅   | 
| SPOON_CLIENT_SECRET      | spoon_client_secret  | `sk_live_` から始まる、Spoon Developpersのコンソールページで発行したClient Secret。この値は漏洩するとbotを乗っ取られるので、適切に管理します。                                                                                                                                                               | ✅   | 
| SPOON_OAUTH_REDIRECT_URL | oauth_redirect_url   | Spoon Developpersのコンソールページで指定したコールバックURL。コンソールで指定したものと1字1句同じである必要があります。本ライブラリを用いて構築した場合、pathは自動的に「/oauth/callback」となります。                                                                                                      | ✅   | 
| SPOON_SECRET_KEY         | secret_key           | ランダムな32文字以上のシークレットキーを生成して指定します。これはSpoon Developpersで発行されるものではありません。sessionのキーなどに利用するので、水平スケールする場合は全てのpodで同一のIDにする必要があります。<br>生成方法の一例: ```openssl rand -base64 22```                                         | ✅   | 
| SPOON_BOT_COUNTRY        | country              | どの国のSpoonで提供するかを指定します。Spoon Developpersでbotを発行したドメインの国と合わせる必要があります。　JP &#124; KR                                                                                                                                                                                  | ✅   | 
| SPOON_BOT_PORT           | port                 | spoonbotを立ち上げるポートを指定します。デフォルトは8080です。                                                                                                                                                                                                                                               |      | 
| SPOON_BOT_NAME           | bot_name             | Oauth連携ページや、Bot招待ページにて表示される名前を指定します。デフォルトは「Spoon Bot」です。                                                                                                                                                                                                              |      | 
|                          | bot_operation_page   | botに関する追加のページを実装し提供する場合、そのパスもしくはURLを指定してください。Bot招待ページに引数で指定したページへ遷移するボタンが出現します。 例えば、web上で入力した値を保存しておき、毎回ライブの最初に送信するといったbotを実装するとき、該当のwebページのパスまたはurlを指定するとよいでしょう。 |      |

## 実行

以下のコマンドで実行し、web上に公開します。必要に応じて上段にNginxなどを設ければよいと思いますが、小規模であればその必要もないと思います。

```bash
python main.py
```

または

```bash
uv run main.py
```

## 連携

Botを連携するには、まず以下のURLを案内します。
https://{your domain}/spoonbot/connect

## 最後に

- このラッパーライブラリは現在ベータ版です
- 本ライブラリは㈱Spoonlabs Japan が提供するオーディオライブプラットフォーム「Spoon」内で利用できるAPIである「[Spoon Developpers](https://developers.spooncast.net/jp)」を便利に利用できるようにしたものですが、本ライブラリおよび開発者は㈱Spoonlabs Japan とは一切関係ありません。