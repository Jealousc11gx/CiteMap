import React from "react";
import { BrowserRouter, Navigate, Routes, Route } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { Dashboard } from "@/pages/Dashboard";
import { Papers } from "@/pages/Papers";
import { Graph } from "@/pages/Graph";
import { Chat } from "@/pages/Chat";
import { PaperDetail } from "@/pages/PaperDetail";
import { Notes } from "@/pages/Notes";
import { Radar } from "@/pages/Radar";
import { ProjectProvider } from "@/contexts/ProjectContext";

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error) {
    console.error("App ErrorBoundary caught:", error);
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 20, color: "red" }}>
          <h1>Something went wrong.</h1>
          <pre>{this.state.error.message}</pre>
          <pre>{this.state.error.stack}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <BrowserRouter>
      <ProjectProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/papers" element={<Papers />} />
            <Route path="/papers/:id" element={<PaperDetail />} />
            <Route path="/graph" element={<Graph />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/notes" element={<Notes />} />
            <Route path="/radar" element={<Radar />} />
            <Route path="/settings/radar" element={<Navigate to="/radar" replace />} />
            <Route path="/settings/radar/cloud" element={<Navigate to="/radar" replace />} />
          </Route>
        </Routes>
      </ProjectProvider>
    </BrowserRouter>
  );
}

export default () => (
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
);
