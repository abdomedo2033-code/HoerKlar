export type RightsStatus = 'PUBLIC_DOMAIN'|'CC0'|'CC_BY'|'CC_BY_SA'|'CC_BY_NC'|'CC_BY_NC_SA'|'CC_BY_ND'|'CC_BY_NC_ND'|'PLATFORM_ONLY'|'EMBED_ONLY'|'LICENSE_REQUIRED'|'UNKNOWN';
export type VideoStatus = 'ACTIVE'|'TEMPORARILY_UNAVAILABLE'|'REMOVED'|'LICENSE_CHANGED'|'EMBED_DISABLED';
export interface SearchFilters { language?:string; license?:RightsStatus[]; durationMin?:number; durationMax?:number; }
export interface VideoCandidate { externalId:string; title:string; provider:string; thumbnailUrl?:string; duration?:number; }
export interface VideoMetadata { externalId:string; title:string; description?:string; language?:string; duration?:number; thumbnailUrl?:string; sourceUrl:string; embedUrl:string; license?:string; licenseUrl?:string; creator?:string; attribution?:string; }
export interface RightsMetadata { status:RightsStatus; license?:string; licenseUrl?:string; attribution?:string; termsUrl?:string; checkedAt:string; }
export interface TranscriptSegment { start:number; end:number; text:string; }
export type Transcript = TranscriptSegment[];
export interface PlaybackSource { type:'mp4'|'webm'|'hls'|'embed'; url:string; embedUrl?:string; }
export interface PlayerAdapter { load(id:string):Promise<void>; play(s:number,e:number):Promise<void>; pause():Promise<void>; seek(t:number):Promise<void>; currentTime():number; onEnded(cb:()=>void):void; setRate(r:number):void; }
export interface VideoProvider {
  providerName:string;
  search(q:string,f?:SearchFilters):Promise<VideoCandidate[]>;
  getVideo(id:string):Promise<VideoMetadata>;
  getRights(id:string):Promise<RightsMetadata>;
  getTranscript?(id:string):Promise<Transcript|null>;
  getPlaybackSource(id:string):Promise<PlaybackSource>;
  supportsEmbedding(id:string):Promise<boolean>;
  supportsTimestampPlayback(id:string):Promise<boolean>;
  createPlayer(videoId:string, container:HTMLElement):PlayerAdapter;
}
export const RIGHTS_ALLOW_FREE = new Set<RightsStatus>(['PUBLIC_DOMAIN','CC0','CC_BY','CC_BY_SA']);
export const RIGHTS_ALLOW_COMMERCIAL = new Set<RightsStatus>(['PUBLIC_DOMAIN','CC0','CC_BY']); // SA needs SA handling
export function commercialAllowed(s:RightsStatus){ return RIGHTS_ALLOW_COMMERCIAL.has(s); }
