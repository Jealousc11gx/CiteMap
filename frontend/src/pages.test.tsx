import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({}),
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
  Link: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('next-themes', () => ({ useTheme: () => ({ theme: 'system', setTheme: vi.fn() }) }));

// Mock UI components
vi.mock('@/components/ui/button', () => ({ Button: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('@/components/ui/input', () => ({ Input: (_props: any) => null }));
vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => children,
  CardContent: ({ children }: { children: React.ReactNode }) => children,
  CardHeader: ({ children }: { children: React.ReactNode }) => children,
  CardTitle: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock('@/components/ui/badge', () => ({ Badge: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('@/components/ui/skeleton', () => ({ Skeleton: () => null }));
vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => children,
  TabsContent: ({ children }: { children: React.ReactNode }) => children,
  TabsList: ({ children }: { children: React.ReactNode }) => children,
  TabsTrigger: ({ children }: { children: React.ReactNode }) => children,
}));

// Mock ErrorAlert
vi.mock('@/components/ErrorAlert', () => ({
  ErrorAlert: () => null,
}));

// Mock lucide-react icons
vi.mock('lucide-react', () => {
  const icons = [
    'Bot', 'User', 'Send', 'Download', 'CheckCircle2', 'AlertCircle', 'RefreshCw',
    'Flame', 'FileText', 'Sparkles', 'BookOpen', 'Search', 'RotateCcw', 'Loader2',
    'ArrowLeft', 'ExternalLink', 'Network', 'Calendar', 'Users', 'Library',
    'TrendingUp', 'ArrowRight', 'Zap', 'Plus', 'Moon', 'Sun', 'X',
    'LayoutDashboard', 'Folder', 'Pencil', 'ChevronRight', 'ChevronDown', 'Save',
    'Trash2',
    'Compass', 'Clock3', 'GitBranch', 'Monitor', 'Eye', 'EyeOff', 'Cloud', 'Radar',
  ];
  const mocked: Record<string, any> = {};
  for (const name of icons) {
    mocked[name] = (_props: any) => React.createElement('span', { 'data-testid': name });
  }
  return mocked;
});

// Mock API services
vi.mock('@/services/api', () => ({
  batchIngest: vi.fn(),
  downloadPdf: vi.fn(),
  fetchPapers: vi.fn(),
  fetchGraphTeam: vi.fn(),
  fetchGraphPaper: vi.fn(),
  fetchPaper: vi.fn(),
  createNoteTemplate: vi.fn(),
  fetchExploreProfiles: vi.fn(),
  fetchExploreCandidates: vi.fn(),
  fetchExploreDigest: vi.fn(),
  fetchExploreTrends: vi.fn(),
  scanExplore: vi.fn(),
  updateExploreTriage: vi.fn(),
  fetchAppSettings: vi.fn(),
  updateAppSettings: vi.fn(),
  updateExploreProfile: vi.fn(),
  fetchRadarConfig: vi.fn(),
  updateRadarConfig: vi.fn(),
  fetchRadarConnection: vi.fn(),
  updateRadarConnection: vi.fn(),
}));

// Mock PixiGraph for lazy import in Graph page
vi.mock('@/components/PixiGraph', () => ({
  PixiGraph: () => null,
}));

describe('Pages smoke tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render Chat page', async () => {
    const mod = await import('./pages/Chat');
    expect(typeof mod.Chat).toBe('function');
  });

  it('should render Dashboard page', async () => {
    const mod = await import('./pages/Dashboard');
    expect(typeof mod.Dashboard).toBe('function');
  });

  it('should render Graph page', async () => {
    const mod = await import('./pages/Graph');
    expect(typeof mod.Graph).toBe('function');
  });

  it('should render Notes page', async () => {
    const mod = await import('./pages/Notes');
    expect(typeof mod.Notes).toBe('function');
  });

  it('should render PaperDetail page', async () => {
    const mod = await import('./pages/PaperDetail');
    expect(typeof mod.PaperDetail).toBe('function');
  });

  it('should render Papers page', async () => {
    const mod = await import('./pages/Papers');
    expect(typeof mod.Papers).toBe('function');
  });

  it('should render Explore page', async () => {
    const mod = await import('./pages/Explore');
    expect(typeof mod.Explore).toBe('function');
  });

  it('should render Settings page', async () => {
    const mod = await import('./pages/Settings');
    expect(typeof mod.Settings).toBe('function');
  });
});
