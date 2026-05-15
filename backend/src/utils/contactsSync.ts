import { google } from 'googleapis';
import { OAuth2Client } from 'google-auth-library';

const GROUP_NAME = 'IT Soporte';
let cachedGroupResourceName: string | null = null;

async function getOrCreateITSoporteGroup(auth: OAuth2Client): Promise<string> {
  if (cachedGroupResourceName) return cachedGroupResourceName;

  const people = google.people({ version: 'v1', auth });
  const res = await people.contactGroups.list({ pageSize: 200 });
  const groups = res.data.contactGroups || [];
  const existing = groups.find(g => g.name === GROUP_NAME);

  if (existing?.resourceName) {
    cachedGroupResourceName = existing.resourceName;
    return existing.resourceName;
  }

  const created = await people.contactGroups.create({
    requestBody: { contactGroup: { name: GROUP_NAME } },
  });

  cachedGroupResourceName = created.data.resourceName!;
  return cachedGroupResourceName;
}

export interface ClienteSyncData {
  nombre: string;
  empresa?: string;
  email?: string;
  telefono?: string;
  ciudad?: string;
  googleContactId?: string;
}

function buildContactBody(cliente: ClienteSyncData, groupResourceName: string) {
  return {
    names: [{ givenName: cliente.nombre }],
    ...(cliente.empresa && { organizations: [{ name: cliente.empresa }] }),
    ...(cliente.email && { emailAddresses: [{ value: cliente.email }] }),
    ...(cliente.telefono && { phoneNumbers: [{ value: cliente.telefono }] }),
    ...(cliente.ciudad && { addresses: [{ city: cliente.ciudad }] }),
    memberships: [{ contactGroupMembership: { contactGroupResourceName: groupResourceName } }],
  };
}

export async function syncContacto(auth: OAuth2Client, cliente: ClienteSyncData): Promise<string | null> {
  try {
    const people = google.people({ version: 'v1', auth });
    const groupResourceName = await getOrCreateITSoporteGroup(auth);

    if (cliente.googleContactId) {
      const current = await people.people.get({
        resourceName: cliente.googleContactId,
        personFields: 'names,emailAddresses,phoneNumbers,organizations,addresses,memberships',
      });

      await people.people.updateContact({
        resourceName: cliente.googleContactId,
        updatePersonFields: 'names,emailAddresses,phoneNumbers,organizations,addresses',
        requestBody: {
          etag: current.data.etag,
          ...buildContactBody(cliente, groupResourceName),
          memberships: undefined,
        },
      });

      return cliente.googleContactId;
    } else {
      const result = await people.people.createContact({
        requestBody: buildContactBody(cliente, groupResourceName),
      });
      return result.data.resourceName || null;
    }
  } catch (error) {
    console.error('Error sincronizando contacto con Google:', error);
    return null;
  }
}

export async function deleteContacto(auth: OAuth2Client, resourceName: string): Promise<void> {
  try {
    const people = google.people({ version: 'v1', auth });
    await people.people.deleteContact({ resourceName });
  } catch (error) {
    console.error('Error eliminando contacto de Google:', error);
  }
}
