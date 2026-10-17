export interface Event {
  id: number;
  title: string;
  address: string;
  lat: number;
  lng: number;
  start_time: string;
  description: string;
  tags: string[]; // 'food' is also provided as one of the tags, so don't need it as separate boolean.
}
