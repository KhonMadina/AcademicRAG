import { test, expect } from '@playwright/test';

test('happy path: create index then chat and render answer', async ({ page }) => {
  const sessionId = 'sess-e2e-1';
  const indexId = 'idx-e2e-1';

  await page.route('http://localhost:8000/**', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname;
    const method = req.method();

    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
      });

    if (method === 'GET' && path === '/health') {
      return json({ status: 'ok', service: 'backend', check: 'liveness' });
    }

    if (method === 'GET' && path === '/sessions') {
      return json({ sessions: [], total: 0 });
    }

    if (method === 'GET' && path === '/models') {
      return json({
        generation_models: ['gemma3:12b-cloud', 'gemma3:4b-cloud'],
        embedding_models: ['Qwen/Qwen3-Embedding-0.6B'],
      });
    }

    if (method === 'POST' && path === '/indexes') {
      return json({ index_id: indexId, reused: false }, 201);
    }

    if (method === 'POST' && path === `/indexes/${indexId}/upload`) {
      return json({
        message: 'Uploaded 1 file',
        uploaded_files: [{ filename: 'sample.txt', stored_path: './uploads/sample.txt' }],
      });
    }

    if (method === 'POST' && path === `/indexes/${indexId}/build`) {
      return json({ message: 'Index build complete', index_id: indexId, status: 'completed' });
    }

    if (method === 'POST' && path === '/sessions') {
      return json({
        session: {
          id: sessionId,
          title: 'E2E Index Session',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          model_used: 'gemma3:12b-cloud',
          message_count: 0,
        },
      }, 201);
    }

    if (method === 'POST' && path === `/sessions/${sessionId}/indexes/${indexId}`) {
      return json({ message: 'Index linked to session' });
    }

    if (method === 'GET' && path === `/sessions/${sessionId}`) {
      return json({
        session: {
          id: sessionId,
          title: 'E2E Index Session',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          model_used: 'gemma3:12b-cloud',
          message_count: 1,
        },
        messages: [],
      });
    }

    if (method === 'GET' && path === `/sessions/${sessionId}/indexes`) {
      return json({
        indexes: [{ id: indexId, index_id: indexId, name: 'E2E Index' }],
        total: 1,
      });
    }

    if (method === 'POST' && path === `/sessions/${sessionId}/messages`) {
      return json({
        response: 'Mocked assistant answer from indexed documents.',
        session: {
          id: sessionId,
          title: 'E2E Index Session',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          model_used: 'gemma3:12b-cloud',
          message_count: 2,
        },
        user_message_id: 'u-msg-1',
        ai_message_id: 'a-msg-1',
        source_documents: [
          {
            chunk_id: 'chunk-1',
            text: 'Evidence text for E2E test.',
            document_id: 'doc-1',
            score: 0.98,
          },
        ],
      });
    }

    return route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ success: false, error: `Unmocked route: ${method} ${path}`, error_code: 'not_found' }),
    });
  });

  await page.route('http://localhost:8001/chat/stream', async (route) => {
    const sse = [
      'data: {"type":"analyze","data":{}}\n\n',
      'data: {"type":"complete","data":{"answer":"Mocked assistant answer from indexed documents.","source_documents":[{"chunk_id":"chunk-1","text":"Evidence text for E2E test."}]}}\n\n',
    ].join('');

    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: sse,
    });
  });

  await page.goto('/');

  await expect(page.getByText('Academic Info')).toBeVisible();
  await page.getByRole('button', { name: 'Create new index' }).click();

  await expect(page.getByRole('heading', { name: 'Create new index' })).toBeVisible();
  await page.getByPlaceholder('My project docs').fill('E2E Index');

  await page.setInputFiles('#file-upload', {
    name: 'sample.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('AcademicRAG e2e content'),
  });

  await page.getByRole('button', { name: 'Start indexing' }).click();
  await page.getByRole('button', { name: 'Start' }).click();

  await expect(page.getByText('What can I help you find today?')).toBeVisible();

  const input = page.getByPlaceholder('Ask anything');
  await input.fill('What does this index contain?');
  await input.press('Enter');

  await expect(page.getByText('Mocked assistant answer from indexed documents.')).toBeVisible();
});
