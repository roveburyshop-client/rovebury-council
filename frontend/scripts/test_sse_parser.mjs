import assert from 'node:assert/strict';

import {
  consumeSSEStream,
  parseSSEEventBlock,
} from '../src/sse.js';


function makeStream(chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(chunk);
      }

      controller.close();
    },
  });
}


function splitBytes(bytes, sizes) {
  const chunks = [];
  let offset = 0;
  let sizeIndex = 0;

  while (offset < bytes.length) {
    const size = sizes[sizeIndex % sizes.length];
    const end = Math.min(
      offset + size,
      bytes.length
    );

    chunks.push(bytes.slice(offset, end));

    offset = end;
    sizeIndex += 1;
  }

  return chunks;
}


async function collectEvents(text, chunkSizes) {
  const encoder = new TextEncoder();
  const bytes = encoder.encode(text);

  const chunks = splitBytes(
    bytes,
    chunkSizes
  );

  const received = [];

  await consumeSSEStream(
    makeStream(chunks),
    (type, event) => {
      received.push({ type, event });
    }
  );

  return received;
}


async function testFragmentedEvents() {
  const events = [
    {
      type: 'stage1_start',
    },
    {
      type: 'stage1_complete',
      data: [
        {
          model: 'test/model',
          response: 'ROVEBURY memória ✓',
        },
      ],
    },
    {
      type: 'stage2_complete',
      metadata: {
        knowledge: {
          used: true,
          sources: [
            'decisions/DEC-001-united-kingdom-primary-market.md',
          ],
          characters: 7222,
        },
      },
    },
    {
      type: 'complete',
    },
  ];

  const text = events
    .map(
      (event) => (
        `data: ${JSON.stringify(event)}\n\n`
      )
    )
    .join('');

  const received = await collectEvents(
    text,
    [1, 2, 3, 5, 8, 13]
  );

  assert.deepEqual(
    received.map((item) => item.event),
    events
  );
}


async function testMultipleEventsInOneChunk() {
  const first = {
    type: 'stage1_start',
  };

  const second = {
    type: 'stage1_complete',
    data: [],
  };

  const text = (
    `data: ${JSON.stringify(first)}\n\n`
    + `data: ${JSON.stringify(second)}\n\n`
  );

  const received = await collectEvents(
    text,
    [10000]
  );

  assert.deepEqual(
    received.map((item) => item.event),
    [first, second]
  );
}


async function testCRLFBoundaries() {
  const event = {
    type: 'title_complete',
    data: {
      title: 'ROVEBURY Council',
    },
  };

  const text = (
    `data: ${JSON.stringify(event)}\r\n\r\n`
  );

  const received = await collectEvents(
    text,
    [4, 1, 7, 2]
  );

  assert.deepEqual(
    received.map((item) => item.event),
    [event]
  );
}


async function testFinalEventWithoutBlankLine() {
  const event = {
    type: 'complete',
  };

  const text = `data: ${JSON.stringify(event)}`;

  const received = await collectEvents(
    text,
    [2, 1, 4]
  );

  assert.deepEqual(
    received.map((item) => item.event),
    [event]
  );
}


function testMultilineDataBlock() {
  const block = (
    'data: {"type":"custom",\n'
    + 'data: "value":"ok"}'
  );

  assert.deepEqual(
    parseSSEEventBlock(block),
    {
      type: 'custom',
      value: 'ok',
    }
  );
}


await testFragmentedEvents();
console.log('PASS  fragmented SSE events');

await testMultipleEventsInOneChunk();
console.log('PASS  multiple SSE events in one chunk');

await testCRLFBoundaries();
console.log('PASS  CRLF SSE boundaries');

await testFinalEventWithoutBlankLine();
console.log('PASS  final event without blank line');

testMultilineDataBlock();
console.log('PASS  multiline SSE data block');

console.log('\nBuffered SSE parser tests PASSED.');
