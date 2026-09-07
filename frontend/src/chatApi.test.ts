import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  listChatSessions,
  createChatSession,
  deleteChatSession,
  getChatMessages,
  sendChatMessage,
  streamChatMessage,
} from './services/api';

// Mock global fetch
declare const global: { fetch: typeof fetch };
const mockFetch = vi.fn();
(global as any).fetch = mockFetch;

describe('Chat API services', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listChatSessions', () => {
    it('should fetch chat sessions', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([{ id: 's1', title: 'Session 1' }]),
      });

      const result = await listChatSessions();
      expect(mockFetch).toHaveBeenCalledWith('/api/chat/sessions');
      expect(result).toEqual([{ id: 's1', title: 'Session 1' }]);
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(listChatSessions()).rejects.toThrow('Failed to list chat sessions');
    });
  });

  describe('createChatSession', () => {
    it('should create a session with title', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: 's1', title: 'New Session', created_at: '2024-01-01' }),
      });

      const result = await createChatSession('New Session');
      expect(mockFetch).toHaveBeenCalledWith('/api/chat/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New Session' }),
      });
      expect(result).toEqual({ id: 's1', title: 'New Session', created_at: '2024-01-01' });
    });

    it('should create a session with empty title', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: 's1', title: '', created_at: '2024-01-01' }),
      });

      const result = await createChatSession();
      expect(mockFetch).toHaveBeenCalledWith('/api/chat/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: '' }),
      });
      expect(result.title).toBe('');
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(createChatSession('Test')).rejects.toThrow('Failed to create chat session');
    });
  });

  describe('deleteChatSession', () => {
    it('should delete a session', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ status: 'deleted' }),
      });

      const result = await deleteChatSession('s1');
      expect(mockFetch).toHaveBeenCalledWith('/api/chat/sessions/s1', {
        method: 'DELETE',
      });
      expect(result).toEqual({ status: 'deleted' });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(deleteChatSession('s1')).rejects.toThrow('Failed to delete chat session');
    });
  });

  describe('getChatMessages', () => {
    it('should fetch messages for a session', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([
          { id: 'm1', role: 'user', content: 'hello' },
          { id: 'm2', role: 'assistant', content: 'hi' },
        ]),
      });

      const result = await getChatMessages('s1');
      expect(mockFetch).toHaveBeenCalledWith('/api/chat/sessions/s1/messages');
      expect(result).toEqual([
        { id: 'm1', role: 'user', content: 'hello' },
        { id: 'm2', role: 'assistant', content: 'hi' },
      ]);
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(getChatMessages('s1')).rejects.toThrow('Failed to get chat messages');
    });
  });

  describe('sendChatMessage', () => {
    it('should send a message', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ id: 'm1', role: 'assistant', content: 'response' }),
      });

      const result = await sendChatMessage('s1', 'hello', 'auto');
      expect(mockFetch).toHaveBeenCalledWith('/api/chat/sessions/s1/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'hello', mode: 'auto' }),
      });
      expect(result).toEqual({ id: 'm1', role: 'assistant', content: 'response' });
    });

    it('should throw on error', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      await expect(sendChatMessage('s1', 'hello')).rejects.toThrow('Failed to send chat message');
    });
  });

  describe('streamChatMessage', () => {
    it('should stream chat events', async () => {
      const mockReader = {
        read: vi.fn()
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"thinking","content":"thinking..."}\n\n') })
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"answer","content":"final answer","papers":[]}\n\n') })
          .mockResolvedValueOnce({ done: true, value: new TextEncoder().encode('') }),
      };

      mockFetch.mockResolvedValue({
        ok: true,
        body: { getReader: () => mockReader },
      });

      const events: any[] = [];
      const fullMessage: any = {};

      await new Promise<void>((resolve, reject) => {
        streamChatMessage(
          's1',
          'hello',
          (event) => { events.push(event); },
          (msg) => { Object.assign(fullMessage, msg); resolve(); },
          (err) => { reject(err); }
        );
      });

      expect(events.length).toBeGreaterThanOrEqual(2);
      expect(events[0].type).toBe('thinking');
      expect(events[events.length - 1].type).toBe('answer');
      expect(fullMessage.content).toBe('final answer');
    });

    it('should stream tool_call and tool_result events', async () => {
      const mockReader = {
        read: vi.fn()
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"tool_call","tool":"search_arxiv","arguments":{"query":"test"}}\n\n') })
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"tool_result","tool":"search_arxiv","result":{"success":true,"papers":[]}}\n\n') })
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"answer","content":"done","papers":[]}\n\n') })
          .mockResolvedValueOnce({ done: true, value: new TextEncoder().encode('') }),
      };

      mockFetch.mockResolvedValue({
        ok: true,
        body: { getReader: () => mockReader },
      });

      const events: any[] = [];
      const fullMessage: any = {};

      await new Promise<void>((resolve, reject) => {
        streamChatMessage(
          's1',
          'hello',
          (event) => { events.push(event); },
          (msg) => { Object.assign(fullMessage, msg); resolve(); },
          (err) => { reject(err); }
        );
      });

      expect(events.some(e => e.type === 'tool_call')).toBe(true);
      expect(events.some(e => e.type === 'tool_result')).toBe(true);
      expect(fullMessage.content).toBe('done');
    });

    it('should handle multiple thinking chunks', async () => {
      const mockReader = {
        read: vi.fn()
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"thinking","content":"chunk1"}\n\n') })
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"thinking","content":"chunk2"}\n\n') })
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"answer","content":"final","papers":[]}\n\n') })
          .mockResolvedValueOnce({ done: true, value: new TextEncoder().encode('') }),
      };

      mockFetch.mockResolvedValue({
        ok: true,
        body: { getReader: () => mockReader },
      });

      const fullMessage: any = {};

      await new Promise<void>((resolve, reject) => {
        streamChatMessage(
          's1',
          'hello',
          () => {},
          (msg) => { Object.assign(fullMessage, msg); resolve(); },
          (err) => { reject(err); }
        );
      });

      expect(fullMessage.content).toBe('final');
    });

    it('should ignore [DONE] events', async () => {
      const mockReader = {
        read: vi.fn()
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: [DONE]\n\n') })
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"answer","content":"after done","papers":[]}\n\n') })
          .mockResolvedValueOnce({ done: true, value: new TextEncoder().encode('') }),
      };

      mockFetch.mockResolvedValue({
        ok: true,
        body: { getReader: () => mockReader },
      });

      const fullMessage: any = {};

      await new Promise<void>((resolve, reject) => {
        streamChatMessage(
          's1',
          'hello',
          () => {},
          (msg) => { Object.assign(fullMessage, msg); resolve(); },
          (err) => { reject(err); }
        );
      });

      expect(fullMessage.content).toBe('after done');
    });

    it('should handle malformed JSON gracefully', async () => {
      const mockReader = {
        read: vi.fn()
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {invalid json}\n\n') })
          .mockResolvedValueOnce({ done: false, value: new TextEncoder().encode('data: {"type":"answer","content":"ok","papers":[]}\n\n') })
          .mockResolvedValueOnce({ done: true, value: new TextEncoder().encode('') }),
      };

      mockFetch.mockResolvedValue({
        ok: true,
        body: { getReader: () => mockReader },
      });

      const fullMessage: any = {};

      await new Promise<void>((resolve, reject) => {
        streamChatMessage(
          's1',
          'hello',
          () => {},
          (msg) => { Object.assign(fullMessage, msg); resolve(); },
          (err) => { reject(err); }
        );
      });

      expect(fullMessage.content).toBe('ok');
    });

    it('should call onError on fetch failure', async () => {
      mockFetch.mockResolvedValue({ ok: false });

      const error = await new Promise<Error>((resolve) => {
        streamChatMessage(
          's1',
          'hello',
          () => {},
          () => {},
          (err) => resolve(err)
        );
      });

      expect(error.message).toBe('Failed to stream chat message');
    });

    it('should call onError when response body is missing', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        body: null,
      });

      const error = await new Promise<Error>((resolve) => {
        streamChatMessage(
          's1',
          'hello',
          () => {},
          () => {},
          (err) => resolve(err)
        );
      });

      expect(error.message).toBe('No response body');
    });
  });
});
