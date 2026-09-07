import { useState, useEffect } from "react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ThemeProvider } from "next-themes";
import App from "@/App";
import "@/index.css";

function Root() {
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const handler = (e: ErrorEvent) => setError(e.message);
    window.addEventListener("error", handler);
    return () => window.removeEventListener("error", handler);
  }, []);
  if (error) return <div style={{ padding: 20, color: "red" }}>ERROR: {error}</div>;
  return <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange={false}>
      <Root />
    </ThemeProvider>
  </StrictMode>,
);
