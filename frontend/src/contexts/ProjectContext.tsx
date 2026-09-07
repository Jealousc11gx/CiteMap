import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { Project } from "@/types";
import {
  createProject as apiCreateProject,
  deleteProject as apiDeleteProject,
  listProjects,
  renameProject as apiRenameProject,
} from "@/services/api";

const STORAGE_KEY = "paper-graph-active-project";

interface ProjectContextValue {
  projects: Project[];
  activeProject: Project | null;
  loading: boolean;
  error: string | null;
  selectProject: (projectId: string) => void;
  createProject: (name: string) => Promise<Project>;
  renameProject: (projectId: string, name: string) => Promise<Project>;
  deleteProject: (projectId: string) => Promise<void>;
  refreshProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(
    () => localStorage.getItem(STORAGE_KEY),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshProjects = async () => {
    try {
      const data = await listProjects();
      setProjects(data);
      setError(null);
      setActiveProjectId((current) => {
        const next = data.some((project) => project.id === current)
          ? current
          : data.find((project) => project.is_system)?.id || data[0]?.id || null;
        if (next) localStorage.setItem(STORAGE_KEY, next);
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshProjects();
  }, []);

  const selectProject = (projectId: string) => {
    if (!projects.some((project) => project.id === projectId)) return;
    localStorage.setItem(STORAGE_KEY, projectId);
    setActiveProjectId(projectId);
  };

  const createProject = async (name: string) => {
    const project = await apiCreateProject(name);
    await refreshProjects();
    localStorage.setItem(STORAGE_KEY, project.id);
    setActiveProjectId(project.id);
    return project;
  };

  const renameProject = async (projectId: string, name: string) => {
    const project = await apiRenameProject(projectId, name);
    await refreshProjects();
    return project;
  };

  const deleteProject = async (projectId: string) => {
    const result = await apiDeleteProject(projectId);
    localStorage.setItem(STORAGE_KEY, result.fallback_project_id);
    setActiveProjectId(result.fallback_project_id);
    await refreshProjects();
  };

  const value = useMemo<ProjectContextValue>(() => ({
    projects,
    activeProject: projects.find((project) => project.id === activeProjectId) || null,
    loading,
    error,
    selectProject,
    createProject,
    renameProject,
    deleteProject,
    refreshProjects,
  }), [projects, activeProjectId, loading, error]);

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  const context = useContext(ProjectContext);
  if (!context) throw new Error("useProject must be used within ProjectProvider");
  return context;
}
