export interface Event {
  id: number;
  organization_id: number,
  timestamp: string;
  title: string;
  description: string;
  address: string;
  longitude: number;
  latitude: number;
  payload: Payload;
}

export interface Payload {
  notes: string,
  tags?: string[],
}

