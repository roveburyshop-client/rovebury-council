/**
 * Buffered Server-Sent Events (SSE) stream utilities.
 *
 * Fetch response chunks do not necessarily align with SSE event boundaries.
 * These helpers preserve partial chunks until a complete event is available.
 */

function findEventBoundary(buffer) {
  const match = /\r?\n\r?\n/.exec(buffer);

  if (!match) {
    return null;
  }

  return {
    index: match.index,
    length: match[0].length,
  };
}


export function parseSSEEventBlock(block) {
  const dataLines = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => {
      const value = line.slice(5);

      return value.startsWith(' ')
        ? value.slice(1)
        : value;
    });

  if (dataLines.length === 0) {
    return null;
  }

  const payload = dataLines.join('\n');

  if (!payload) {
    return null;
  }

  return JSON.parse(payload);
}


export async function consumeSSEStream(stream, onEvent) {
  if (!stream) {
    throw new Error('Streaming response body is unavailable');
  }

  const reader = stream.getReader();
  const decoder = new TextDecoder();

  let buffer = '';

  const processBlock = (block) => {
    if (!block.trim()) {
      return;
    }

    try {
      const event = parseSSEEventBlock(block);

      if (event && event.type) {
        onEvent(event.type, event);
      }
    } catch (error) {
      console.error(
        'Failed to parse SSE event:',
        error,
        block
      );
    }
  };

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      buffer += decoder.decode();
      break;
    }

    buffer += decoder.decode(
      value,
      { stream: true }
    );

    while (true) {
      const boundary = findEventBoundary(buffer);

      if (!boundary) {
        break;
      }

      const block = buffer.slice(
        0,
        boundary.index
      );

      buffer = buffer.slice(
        boundary.index + boundary.length
      );

      processBlock(block);
    }
  }

  // Be tolerant of a final SSE event that is not followed by a blank line.
  if (buffer.trim()) {
    processBlock(buffer);
  }
}
