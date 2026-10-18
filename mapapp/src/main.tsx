import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import EventTagsProvider from "./components/events/EventTagsProvider";
import { AuthProvider } from "./components/auth/AuthProvider";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider><EventTagsProvider><App /></EventTagsProvider></AuthProvider>
  </React.StrictMode>
);
