import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  fetchPapers,
  fetchPaper,
  updatePaperVenue,
  searchArxivResults,
  batchIngest,
  downloadPdf,
  ingestPdf,
  ingestArxiv,
  searchArxiv,
  annotatePaper,
  batchAnnotate,
  fetchLLMModels,
  fetchGraphTeam,
  fetchGraphTeamEgo,
  fetchGraphPaper,
  fetchGraphCitation,
  fetchGraphSimilarity,
  syncPaperCitations,
  syncCitationMetrics,
  listNotes,
  getNote,
  saveNote,
  createNoteTemplate,
  deleteNote,
} from './api';

// Mock global fetch
declare const global: { fetch: typeof fetch };
const mockFetch = vi.fn();
(global as any).fetch = mockFetch;

describe('API services', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('fetchPapers', () => {
    it('should fetch papers without params', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([{ id: '1', title: 'Test' }]),
      });

      const result = await fetchPapers();
      expect(mockFetch).toHaveBeenCalledWith('/api/papers');
      expect(result).toEqual([{ id: '1', title: 'Test' }]);
    });

    it('should fetch papers with query params', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([{ id: '1', title: 'Test' }]),
      });

      const result = await fetchPapers('arxiv', 'test query');
      expect(mockFetch).toHaveBeenCalledWith('/api/papers?source=arxiv&q=test+query');
      expect(result).toEqual([{ id: '1', title: 'Test' }]);
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(fetchPapers()).rejects.toThrow('Failed to fetch papers');
    });
  });

  describe('fetchPaper', () => {
    it('should fetch single paper', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: '1', title: 'Test' }),
      });

      const result = await fetchPaper('1');
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/1');
      expect(result).toEqual({ id: '1', title: 'Test' });
    });
  });

  describe('updatePaperVenue', () => {
    it('should persist a manual venue override', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: 'paper/1', venue: 'AAAI', venue_year: 2026 }),
      });

      const result = await updatePaperVenue('paper/1', 'AAAI', 2026);
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/paper%2F1/venue', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ venue: 'AAAI', venue_year: 2026 }),
      });
      expect(result.venue).toBe('AAAI');
    });
  });

  describe('searchArxivResults', () => {
    it('should search arxiv without downloading', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ results: [{ id: '1', title: 'Test' }] }),
      });

      const result = await searchArxivResults('test query', 5);
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/search-arxiv?q=test+query&max_results=5');
      expect(result).toEqual({ results: [{ id: '1', title: 'Test' }] });
    });
  });

  describe('batchIngest', () => {
    it('should batch ingest papers', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ results: [{ id: '1', status: 'success' }] }),
      });

      const result = await batchIngest(['arxiv_1', 'arxiv_2']);
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/batch-ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper_ids: ['arxiv_1', 'arxiv_2'], download_pdf: false }),
      });
      expect(result).toEqual({ results: [{ id: '1', status: 'success' }] });
    });
  });

  describe('downloadPdf', () => {
    it('should download pdf for paper', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ status: 'success', pdf_path: '/path/to/pdf' }),
      });

      const result = await downloadPdf('arxiv_1');
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/arxiv_1/download-pdf', {
        method: 'POST',
      });
      expect(result).toEqual({ status: 'success', pdf_path: '/path/to/pdf' });
    });
  });

  describe('ingestPdf', () => {
    it('should ingest a PDF file', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ paper_id: 'p1', title: 'Test Paper' }),
      });

      const file = new File(['pdf content'], 'test.pdf');
      const result = await ingestPdf(file);

      const [url, options] = mockFetch.mock.calls[0];
      expect(url).toBe('/api/papers/ingest-pdf');
      expect(options.method).toBe('POST');
      expect(options.body).toBeInstanceOf(FormData);
      expect(options.body.get('file')).toBe(file);
      expect(result).toEqual({ paper_id: 'p1', title: 'Test Paper' });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      const file = new File(['pdf content'], 'test.pdf');
      await expect(ingestPdf(file)).rejects.toThrow('Failed to ingest PDF');
    });
  });

  describe('ingestArxiv', () => {
    it('should ingest an arXiv paper with default options', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ paper_id: 'arxiv_1', title: 'Test' }),
      });

      const result = await ingestArxiv('arxiv_1');
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/ingest-arxiv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ arxiv_id: 'arxiv_1', download_pdf: false }),
      });
      expect(result).toEqual({ paper_id: 'arxiv_1', title: 'Test' });
    });

    it('should ingest an arXiv paper and download the PDF', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ paper_id: 'arxiv_1', title: 'Test' }),
      });

      const result = await ingestArxiv('arxiv_1', true);
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/ingest-arxiv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ arxiv_id: 'arxiv_1', download_pdf: true }),
      });
      expect(result).toEqual({ paper_id: 'arxiv_1', title: 'Test' });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(ingestArxiv('arxiv_1')).rejects.toThrow('Failed to ingest arXiv');
    });
  });

  describe('searchArxiv', () => {
    it('should search arXiv with default params', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ results: [{ id: '1', title: 'Test' }] }),
      });

      const result = await searchArxiv('test query');
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/papers/search?q=test+query&max_results=10&download=false'
      );
      expect(result).toEqual({ results: [{ id: '1', title: 'Test' }] });
    });

    it('should search arXiv with explicit params', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ results: [{ id: '1', title: 'Test' }] }),
      });

      const result = await searchArxiv('test query', 5, true);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/papers/search?q=test+query&max_results=5&download=true'
      );
      expect(result).toEqual({ results: [{ id: '1', title: 'Test' }] });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(searchArxiv('test query')).rejects.toThrow('Failed to search arXiv');
    });
  });

  describe('annotatePaper', () => {
    it('should annotate a paper with the default model', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ summary: 'A summary' }),
      });

      const result = await annotatePaper('paper%2F1');
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/paper%252F1/annotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper_id: 'paper%2F1' }),
      });
      expect(result).toEqual({ summary: 'A summary' });
    });

    it('should annotate a paper with a custom model', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ summary: 'A summary' }),
      });

      const result = await annotatePaper('paper_1', 'gpt-4o');
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/paper_1/annotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ paper_id: 'paper_1', model: 'gpt-4o' }),
      });
      expect(result).toEqual({ summary: 'A summary' });
    });

    it('should force re-annotate an existing paper', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ summary: 'A refreshed summary' }),
      });

      await annotatePaper('paper_1', 'gpt-4o', 'project_1', true);

      expect(mockFetch).toHaveBeenCalledWith('/api/papers/paper_1/annotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          paper_id: 'paper_1',
          model: 'gpt-4o',
          project_id: 'project_1',
          force: true,
        }),
      });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(annotatePaper('paper_1')).rejects.toThrow('Failed to annotate paper');
    });

    it('should expose backend error code and reason', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({
          detail: { code: 'ANNOTATE_ABSTRACT_MISSING', error: '论文摘要为空，无法进行智能标注' },
        }),
      });

      await expect(annotatePaper('paper_1')).rejects.toThrow(
        '[ANNOTATE_ABSTRACT_MISSING] 论文摘要为空，无法进行智能标注',
      );
    });
  });

  describe('fetchLLMModels', () => {
    it('should fetch available models and default model', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          models: ['deepseek-v4-flash', 'deepseek-v4-pro'],
          default_model: 'deepseek-v4-flash',
        }),
      });

      const result = await fetchLLMModels();
      expect(mockFetch).toHaveBeenCalledWith('/api/llm/models');
      expect(result.default_model).toBe('deepseek-v4-flash');
    });
  });

  describe('batchAnnotate', () => {
    it('should batch annotate papers with the default model', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ results: [{ id: '1', status: 'success' }] }),
      });

      const result = await batchAnnotate();
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/batch-annotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      expect(result).toEqual({ results: [{ id: '1', status: 'success' }] });
    });

    it('should batch annotate papers with a custom model', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ results: [{ id: '1', status: 'success' }] }),
      });

      const result = await batchAnnotate('gpt-4o');
      expect(mockFetch).toHaveBeenCalledWith('/api/papers/batch-annotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: 'gpt-4o' }),
      });
      expect(result).toEqual({ results: [{ id: '1', status: 'success' }] });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(batchAnnotate('gpt-4o')).rejects.toThrow('Failed to batch annotate');
    });
  });

  describe('fetchGraphTeam', () => {
    it('should fetch the team graph', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ nodes: [], links: [] }),
      });

      const result = await fetchGraphTeam();
      expect(mockFetch).toHaveBeenCalledWith('/api/graph/team');
      expect(result).toEqual({ nodes: [], links: [] });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(fetchGraphTeam()).rejects.toThrow('Failed to fetch team graph');
    });
  });

  describe('fetchGraphTeamEgo', () => {
    it('should fetch the inferred team ego graph for a project', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ nodes: [], edges: [] }),
      });

      const result = await fetchGraphTeamEgo('project 1');
      expect(mockFetch).toHaveBeenCalledWith('/api/graph/team-ego?project_id=project%201');
      expect(result).toEqual({ nodes: [], edges: [] });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(fetchGraphTeamEgo()).rejects.toThrow('Failed to fetch team ego graph');
    });
  });

  describe('fetchGraphPaper', () => {
    it('should fetch the paper graph', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ nodes: [], links: [] }),
      });

      const result = await fetchGraphPaper();
      expect(mockFetch).toHaveBeenCalledWith('/api/graph/paper');
      expect(result).toEqual({ nodes: [], links: [] });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(fetchGraphPaper()).rejects.toThrow('Failed to fetch paper graph');
    });
  });

  describe('citation graph APIs', () => {
    it('should batch sync project citation metrics', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ updated: 20, skipped: 1 }),
      });

      await expect(syncCitationMetrics('project 1')).resolves.toEqual({ updated: 20, skipped: 1 });
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/papers/sync-citation-metrics?project_id=project%201',
        { method: 'POST' },
      );
    });

    it('should sync citations and load both citation graph modes', async () => {
      mockFetch
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ citation_count: 12 }) })
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ nodes: [], edges: [] }) })
        .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ nodes: [], edges: [] }) });

      await expect(syncPaperCitations('paper 1')).resolves.toEqual({ citation_count: 12 });
      await expect(fetchGraphCitation('paper 1')).resolves.toEqual({ nodes: [], edges: [] });
      await expect(fetchGraphSimilarity('paper 1')).resolves.toEqual({ nodes: [], edges: [] });
      expect(mockFetch).toHaveBeenNthCalledWith(1, '/api/papers/paper%201/sync-citations', { method: 'POST' });
      expect(mockFetch).toHaveBeenNthCalledWith(2, '/api/graph/citation?paper_id=paper+1&limit_per_direction=12');
      expect(mockFetch).toHaveBeenNthCalledWith(3, '/api/graph/similarity?paper_id=paper%201');
    });

    it('should expose the citation sync error detail', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ detail: 'Semantic Scholar 请求频率受限' }),
      });

      await expect(syncPaperCitations('paper')).rejects.toThrow('Semantic Scholar 请求频率受限');
    });
  });

  describe('listNotes', () => {
    it('should list notes', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([{ paper_id: '1', content: 'Note' }]),
      });

      const result = await listNotes();
      expect(mockFetch).toHaveBeenCalledWith('/api/notes');
      expect(result).toEqual([{ paper_id: '1', content: 'Note' }]);
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(listNotes()).rejects.toThrow('Failed to list notes');
    });
  });

  describe('getNote', () => {
    it('should get a note', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ paper_id: 'paper 1', content: 'Note' }),
      });

      const result = await getNote('paper 1');
      expect(mockFetch).toHaveBeenCalledWith('/api/notes/paper%201');
      expect(result).toEqual({ paper_id: 'paper 1', content: 'Note' });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(getNote('paper_1')).rejects.toThrow('Failed to get note');
    });
  });

  describe('saveNote', () => {
    it('should save a note', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      });

      const result = await saveNote('paper 1', 'Updated note');
      expect(mockFetch).toHaveBeenCalledWith('/api/notes/paper%201', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: 'Updated note' }),
      });
      expect(result).toEqual({ success: true });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(saveNote('paper_1', 'Note')).rejects.toThrow('Failed to save note');
    });
  });

  describe('createNoteTemplate', () => {
    it('should create a note template', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      });

      const result = await createNoteTemplate('paper 1');
      expect(mockFetch).toHaveBeenCalledWith('/api/notes/paper%201/template', {
        method: 'POST',
      });
      expect(result).toEqual({ success: true });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(createNoteTemplate('paper_1')).rejects.toThrow('Failed to create note template');
    });
  });

  describe('deleteNote', () => {
    it('should delete a note', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      });

      const result = await deleteNote('paper 1');
      expect(mockFetch).toHaveBeenCalledWith('/api/notes/paper%201', {
        method: 'DELETE',
      });
      expect(result).toEqual({ success: true });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(deleteNote('paper_1')).rejects.toThrow('Failed to delete note');
    });
  });
});
