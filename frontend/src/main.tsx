import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { Auth0Provider } from "@auth0/auth0-react";
import "./index.css";

const domain = import.meta.env.VITE_AUTH0_DOMAIN;
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {domain && clientId ? (
      <Auth0Provider
        domain={domain}
        clientId={clientId}
        authorizationParams={{ redirect_uri: window.location.origin }}
      >
        <App />
      </Auth0Provider>
    ) : (
      <main className="auth-configuration-error" role="alert">
        <h1>Account configuration missing</h1>
        <p>Set VITE_AUTH0_DOMAIN and VITE_AUTH0_CLIENT_ID in frontend/.env, then restart the development server.</p>
      </main>
    )}
  </React.StrictMode>
);
