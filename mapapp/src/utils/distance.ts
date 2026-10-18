import type { Event } from "../types";

export function calculate_distance(user_location: [number, number], event: Event): number {
    const [user_lat, user_lng] = user_location;
    const delta_y = 113320 * (user_lat - event.latitude);
    const delta_x = 113320 * Math.cos(degreesToRadians((user_lat + event.latitude) / 2)) * (user_lng - event.longitude);
 
    return Math.sqrt(delta_x * delta_x + delta_y * delta_y);
}

function degreesToRadians(degrees: number) {
    return degrees*(Math.PI / 180);
}