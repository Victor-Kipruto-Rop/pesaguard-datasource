import {readFileSync} from 'node:fs';
import {describe, expect, it} from 'vitest';

const css = readFileSync(new URL('./glass-theme.css', import.meta.url), 'utf8');

describe('PesaGuard glass theme contract', () => {
  it('defines the shared emerald glass tokens and page canvas', () => {
    expect(css).toContain('--pg-glass:');
    expect(css).toContain('--pg-glass-border:');
    expect(css).toContain('--pg-glass-blur:');
    expect(css).toContain('background-attachment:fixed');
    expect(css).toContain('#07140d');
  });

  it('keeps glass effects scoped to named surfaces rather than substring-matching arbitrary classes', () => {
    expect(css).toContain('.panel,.metric-card');
    expect(css).not.toMatch(/^\\s*\\[class\\*=/m);
  });

  it('preserves keyboard focus and reduced-motion/transparency accommodations', () => {
    expect(css).toContain(':focus-visible');
    expect(css).toContain('prefers-reduced-motion:reduce');
    expect(css).toContain('prefers-reduced-transparency:reduce');
  });

  it('keeps form controls readable on the dark emerald canvas', () => {
    expect(css).toContain('input:focus');
    expect(css).toContain('select option');
    expect(css).toContain('input::placeholder');
  });
});
