import { describe, it, expect, vi } from 'vitest';

// Mock UI components that can't be resolved in node environment
vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: () => null,
}));

vi.mock('@/components/ui/button', () => ({
  Button: () => null,
}));

vi.mock('@/components/ui/input', () => ({
  Input: () => null,
}));

vi.mock('@/components/ui/card', () => ({
  Card: () => null,
  CardContent: () => null,
}));

vi.mock('@/components/ui/badge', () => ({
  Badge: () => null,
}));

vi.mock('@/components/ErrorAlert', () => ({
  ErrorAlert: () => null,
}));

vi.mock('lucide-react', () => ({
  Upload: () => null,
  Search: () => null,
  Sparkles: () => null,
  Download: () => null,
  FileText: () => null,
  CheckCircle2: () => null,
  AlertCircle: () => null,
}));

// Mock the API module
vi.mock('./services/api', () => ({
  fetchPapers: vi.fn(),
  ingestPdf: vi.fn(),
  ingestArxiv: vi.fn(),
  searchArxivResults: vi.fn(),
  annotatePaper: vi.fn(),
  downloadPdf: vi.fn(),
  batchIngest: vi.fn(),
  batchAnnotate: vi.fn(),
}));

describe('Papers page', () => {
  it('is a valid React component', async () => {
    const mod = await import('./pages/Papers');
    expect(typeof mod.Papers).toBe('function');
  });
});
