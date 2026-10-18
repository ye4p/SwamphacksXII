# SwamphacksXII
UF Event Tracker

Overstimulated by the sheer number of clubs and events at any given day? 
The UF Event Tracker has you covered!


The UF Event Tracker acts as a complete registry for clubs and their events. Think GatorConnect, but more streamlined and focused on user convenience.


Who is this for?
Where GatorConnect is more for the logistical side, and therefore caters to club officers, the UF Event Tracker specializes to the student who wants to explore organizations. It allows the student to explore the many options and opportunities without feeling overwhelmed.

Example Case
John is a Computer Science student. He wants to know what club meetings he can go to this week. He creates an account on the UF Event Tracker and filters by Workshops and Engineering, two of many tags that clubs assign to themselves and their events. John picks a few that fit in his schedule and the website imports the calendars as .ics files. After going to the events, he favorites the clubs that he liked and those show up in his recommendations. Next week, his favorite clubs have events that appear at the top, and he continues exploring…


## Authentication setup

The frontend uses Auth0 Universal Login through `@auth0/auth0-react`.
Copy `frontend/.env.example` to `frontend/.env` for a new checkout (preserve any existing map settings), then restart Vite. `VITE_AUTH0_DOMAIN` and `VITE_AUTH0_CLIENT_ID` are public SPA configuration; no client secret is needed.

In the Auth0 dashboard, configure this application as a **Single Page Application** and add `http://localhost:5173` to **Allowed Callback URLs**, **Allowed Logout URLs**, and **Allowed Web Origins**. Add the deployed site's origin to all three lists when deploying. The app uses `window.location.origin` for login and logout redirects.

Run `npm run dev` from `frontend`, then choose **Sign up** or **Log in**. Complete authentication on Auth0's hosted page; the header shows your name/email and **Log out** after returning. Event browsing remains available while signed out or while the SDK loads. Authentication errors appear next to the account controls.

Reference: [Auth0 React authentication guide](https://developer.auth0.com/resources/guides/spa/react/basic-authentication).
