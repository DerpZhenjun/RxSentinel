import { describe, it, expect } from 'vitest';
import {
  buildRowMetrics,
  findIndexAtOffset,
  scrollTopToCenterIndex,
  estimateRowHeight,
} from './feedRowMetrics.js';

describe('feedRowMetrics', () => {
  it('offsets are monotonic and sum heights', () => {
    const items = [
      { content: '短', analysis: 'a', threadParent: '' },
      { content: 'x'.repeat(120), analysis: 'y'.repeat(80), threadParent: '父评'.repeat(20) },
      { content: 'SugarLane', analysis: '研判', threadParent: '' },
    ];
    const { heights, offsets, total } = buildRowMetrics(items);
    expect(offsets[0]).toBe(0);
    expect(offsets[1]).toBe(heights[0]);
    expect(total).toBe(offsets[items.length]);
    expect(heights[1]).toBeGreaterThan(heights[0]);
  });

  it('scrollTopToCenterIndex uses prefix offsets not fixed stride', () => {
    const items = Array.from({ length: 40 }, (_, i) => ({
      content: i % 5 === 0 ? '长'.repeat(80) : '短',
      analysis: '测',
      threadParent: i % 7 === 0 ? '父'.repeat(30) : '',
    }));
    const { offsets, heights } = buildRowMetrics(items);
    const idx = 35;
    const fixed = idx * 248;
    const variable = scrollTopToCenterIndex(offsets, heights, idx, 500);
    expect(Math.abs(variable - fixed)).toBeGreaterThan(100);
    expect(findIndexAtOffset(offsets, variable)).toBeGreaterThanOrEqual(idx - 2);
  });

  it('estimateRowHeight grows with thread parent', () => {
    const base = estimateRowHeight({ content: 'a', analysis: 'b' });
    const withParent = estimateRowHeight({ content: 'a', analysis: 'b', threadParent: '父评内容' });
    expect(withParent).toBeGreaterThan(base);
  });
});
