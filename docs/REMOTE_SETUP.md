# Remote messages: what to create and where to paste it

Everything is pasted in **Settings › Connections › Remote messages** on `http://walloftext.local/`.
Secrets are stored in `/var/lib/walloftext/secrets.json` (mode 0600). They are never shown again,
never logged and never included in backups.

## Email (free)

1. Create a **new personal Gmail account** just for the printer, e.g. `yourname.printer@gmail.com`.
   Don't use a Google Workspace (work/school) address: those need OAuth, which this doesn't do.
2. In that account: Google Account › Security › turn on **2-Step Verification**.
3. Google Account › Security › **App passwords** › create one (name it "Wall Printer").
   You get 16 letters like `abcd efgh ijkl mnop`.
4. In the app: Remote messages › **Email** › enter the address and the app password › **Save and test**.
5. Add yourself under **Allowed senders** with the address you'll send *from*.

The printer checks the inbox every minute and marks what it reads as read. Mail only counts when
Gmail's `Authentication-Results` shows SPF or DKIM passing for the sender's domain, so a forged
From line is treated as a stranger and dropped. Another provider works if it offers IMAP with an
app password: open "Not Gmail?" and set its IMAP server.

## Telegram (free)

1. In Telegram, open a chat with **@BotFather** and send `/newbot`. Pick a name and a username
   ending in `bot`. BotFather replies with a **token** like `123456789:AA…`.
2. In the app: Remote messages › **Telegram** › paste the token › **Save and test**
   (it shows `Connected as @yourbot`).
3. Press **Add me**, then send your bot any message within 5 minutes. The app shows your name and
   numeric ID; press **Yes, allow**. Repeat for each family member (each presses Add me in turn).

The bot replies "Printed" when a message comes out, or "Queued: the printer is out of paper".
Photos are printed too (dithered, with the paper-safe limiter on).

## SMS (optional, paid): not set up

A text to an ordinary number can only reach the Pi through a paid number (e.g. Twilio, which
needs a UK regulatory bundle and a monthly fee) or a SIM modem. Telegram is the free way to get
text-message behaviour. Say if you want SMS and which route, and it can be added as one more adapter.

## Rules that apply to every channel

- Only allowed senders print. Others are dropped and counted ("3 blocked this week").
- Per sender: "Print straight away" or "Wait for my OK" (SMS senders default to waiting).
  Waiting messages appear in Settings › Access › Waiting for your OK, together with guest notes.
- At most 10 messages per sender per hour, and the shared daily limit (Settings › Schedules).
- Quiet hours hold messages until they end. Offline or out of paper: they wait in the queue.
- Long messages are cut at 600 characters or 40 lines ("… (cut)"); adjustable in settings.
- A message is never printed twice, even after a restart.

## Telegram bot commands

Settings › Telegram (also reached from the Telegram row in Remote messages):

- **How messages print:** default style (message slip, plain text, big text, checklist) and text
  size. Turn on **Ask how to print each message** to get buttons after every message.
- **Commands:** /help, /settings, /templates and /cancel are built in. Add your own: reply with
  text (e.g. /wifi with the guest password, as a block to copy), print something (weather,
  fortune, a routine), or set how the next message prints (e.g. /big).
- **Templates:** text that /templates sends back to copy, fill in and send.

