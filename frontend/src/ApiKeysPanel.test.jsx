// @vitest-environment jsdom
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';

const apiMock = vi.hoisted(() => vi.fn());
vi.mock('./api.js', () => ({ api: apiMock }));

import ApiKeysPanel from './ApiKeysPanel.jsx';

const reply = data => ({ status: 200, json: async () => data });
function configureIdentity({production_key_eligible=false}={}) {
  apiMock.mockImplementation(async path => {
    if (path === '/api/v1/keys') return reply({items:[{id:'key-a',name:'Sandbox integration',environment:'sandbox',status:'active',key_prefix:'pg_sandbox_demo',scopes:['registry:read'],created_at:'2026-10-01T00:00:00Z'}]});
    if (path.startsWith('/api/v1/keys/audit/events')) return reply({items:[]});
    if (path === '/api/v1/keys/me') return reply({user_id:'test-user',organization_id:'test-org',tenant_id:'test-org',roles:['owner'],organization_verified:production_key_eligible,production_key_eligible,token_expires_at:1900000000});
    throw new Error('Unexpected API request: '+path);
  });
}

afterEach(() => { cleanup(); vi.clearAllMocks(); });
beforeEach(() => { configureIdentity(); });

describe('API key management UI', () => {
  it('validates the PesaGuard access token against the backend and shows the scoped key list', async () => {
    render(<ApiKeysPanel />);
    fireEvent.change(screen.getByPlaceholderText('Paste short-lived access token'), {target:{value:'test-access-token'}});
    fireEvent.click(screen.getByRole('button', {name:'Connect PesaGuard account'}));
    expect(await screen.findByText(/PesaGuard access token accepted/)).toBeTruthy();
    expect(await screen.findByText('Sandbox integration')).toBeTruthy();
    expect(apiMock).toHaveBeenCalledWith('/api/v1/keys/me', expect.objectContaining({headers:expect.objectContaining({Authorization:'Bearer test-access-token'})}));
  });

  it('disables key creation in preview mode after identity verification', async () => {
    render(<ApiKeysPanel readOnly />);
    fireEvent.change(screen.getByPlaceholderText('Paste short-lived access token'), {target:{value:'test-access-token'}});
    fireEvent.click(screen.getByRole('button', {name:'Connect PesaGuard account'}));
    await screen.findByText(/PesaGuard access token accepted/);
    expect(screen.getByRole('button', {name:/Generate sandbox key/i}).disabled).toBe(true);
  });

  it('does not enable production key issuance without verified organization claims', async () => {
    render(<ApiKeysPanel />);
    fireEvent.change(screen.getByPlaceholderText('Paste short-lived access token'), {target:{value:'test-access-token'}});
    fireEvent.click(screen.getByRole('button', {name:'Connect PesaGuard account'}));
    await screen.findByText(/PesaGuard access token accepted/);
    fireEvent.change(screen.getByLabelText('Environment'), {target:{value:'production'}});
    expect(screen.getByRole('button', {name:/Generate production key/i}).disabled).toBe(true);
    expect(screen.getByText(/Production key issuance is unavailable/)).toBeTruthy();
  });

  it('filters keys with the page search field', async () => {
    render(<ApiKeysPanel />);
    fireEvent.change(screen.getByPlaceholderText('Paste short-lived access token'), {target:{value:'test-access-token'}});
    fireEvent.click(screen.getByRole('button', {name:'Connect PesaGuard account'}));
    await screen.findByText('Sandbox integration');
    fireEvent.change(screen.getByRole('textbox', {name:'Filter API keys and audit events'}), {target:{value:'does-not-match'}});
    await waitFor(() => expect(screen.queryByText('Sandbox integration')).toBeNull());
    expect(screen.getByText('No API keys match this filter')).toBeTruthy();
  });
});
