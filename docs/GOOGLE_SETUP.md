# Connect Google Calendar and Google Tasks

Wall of Text reads your calendars and tasks through Google's own APIs. It can only read them,
never change them. Both are free for personal use: no billing account is needed, and the daily
limits are far above what a printer uses.

Google needs a project of your own before an app like this can read your data. You do this once,
on a computer, in about 10 minutes. After that everything happens in the Wall of Text app.

## 1. Make your Google project (once, on a computer)

1. Open https://console.cloud.google.com/ and sign in with the Google account that has your
   calendar and tasks.
2. Click the project picker at the top, then **New project**. Name it "Wall of Text" and click
   **Create**. Make sure the new project is selected at the top.
3. Go to **APIs & Services › Library**. Search for **Google Calendar API**, open it and click
   **Enable**. Do the same for **Google Tasks API**.
4. Go to **APIs & Services › OAuth consent screen** (on newer screens: **Google Auth Platform**)
   and choose the **user type**. Wall of Text works the same with either.

   **Internal** (only if your account is in a Google Workspace organisation, for example a
   company domain):
   - Choose **Internal**, enter an app name ("Wall of Text") and your email, and save.
   - That's all: no home page, no test users, no publishing, no 7-day limit, and no
     "unverified app" warning. Only accounts in your organisation can sign in, so you sign in
     with that work account and print its calendar and tasks.

   **External** (any Gmail account; Internal isn't offered to plain Gmail):
   - Choose **External**, enter an app name ("Wall of Text") and your email, and save.
   - On the **Branding** page, Google needs a home page and a privacy policy before it lets an
     External app go to production. Use the project's GitHub Pages:
     - Application home page: `https://keyquesttech.github.io/Wall-of-text/`
     - Privacy policy: `https://keyquesttech.github.io/Wall-of-text/privacy.html`
     - Authorized domain: `keyquesttech.github.io`

     (These pages live in this repo's `docs/` folder. GitHub Pages must be on: repo
     **Settings › Pages › Deploy from a branch › `main` / `/docs`**.)
   - Under **Test users** (or **Audience**), add your own Gmail address.
   - Set **Publishing status** to **In production**: **Publish app**, then **Confirm** when Google
     says the app needs verification. It works unverified for up to 100 users. This matters: in
     "Testing", Google ends the sign-in after 7 days and your prints say "Sign in again".
5. Go to **APIs & Services › Credentials › Create credentials › OAuth client ID**.
   - **Application type: Desktop app.** (Not "Web application": Google doesn't allow a web
     client to return to `walloftext.local`.)
   - Click **Create**. Keep the window with the **Client ID** and **Client secret** open.

## 2. Connect in the app (from your phone or computer)

1. Open http://walloftext.local/ and go to **Settings › Google Calendar & Tasks**.
2. Paste the **Client ID** and **Client secret**, then tap **Save and continue**.
3. Tap **Sign in with Google** and choose your account (with an Internal project, your account
   in that organisation).
   - External only: if Google says the app isn't verified, tap **Advanced › Go to Wall of Text (unsafe)**.
     It's your own project.
   - Tick the boxes for Calendar and Tasks and tap **Continue**.
4. The next page says it **can't be reached** (its address starts
   `http://127.0.0.1:53682/`). That's expected: Google only lets this kind of app return to the
   device's own address. Copy the **whole address** from the address bar.
   - iPhone Safari: tap the address bar, then tap and hold the address and choose **Copy**.
   - Android Chrome: tap the address bar, then the copy icon.
5. Go back to the Wall of Text tab, paste it into the box and tap **Connect**. The code inside
   works once and only for a few minutes, so do this straight away.
6. Choose which **calendars** and **task lists** to print. With nothing chosen, the app uses your
   main calendar and your first task list.

## Where things are kept

- The client secret and the sign-in (refresh token) are stored on the Pi in
  `/var/lib/walloftext/secrets.json` (readable by the app only). They are never in backups,
  logs or the Git repository.
- **Disconnect Google** in the app signs out and asks Google to cancel the sign-in. You can also
  remove access at https://myaccount.google.com/permissions.

## If something goes wrong

| Message | What to do |
|---|---|
| "Sign in again" | Google cancelled the sign-in (password change, 7-day "Testing" limit on an External project, an admin policy on an Internal one, or access removed). For External, check step 1.4 is **In production**. Then tap **Sign in again**. |
| "Turn on the Google Calendar API / Tasks API" | Step 1.3 was missed. Enable it, wait a minute, try again. |
| "Google didn't accept the client ID or secret" | Copy both again from **Credentials** (step 1.5). |
| "That sign-in has expired" | Tap **Sign in with Google** again and paste the new address straight away. |
| Google's page says **"Access blocked: … can only be used within its organization"** (`org_internal`) | The project is Internal and you chose an account outside the organisation. Sign in with your organisation account, or switch the project to External (step 1.4). |
| "Connected, but without calendar/tasks" | You un-ticked a box on Google's page. Disconnect, sign in again and tick both. |
