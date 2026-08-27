import type { VideoProvider, VideoCandidate, VideoMetadata, RightsMetadata, PlaybackSource, PlayerAdapter } from './types';
import { HTML5Player } from '../player/html5';
const OAI='https://www.openbeelden.nl/feeds/oai/';
function mapRights(dcRights:string):RightsMetadata['status']{
  const r=(dcRights||'').toLowerCase();
  if(r.includes('cc0')) return 'CC0';
  if(r.includes('by-sa')) return r.includes('nc')?'CC_BY_NC_SA':'CC_BY_SA';
  if(r.includes('by-nc-nd')) return 'CC_BY_NC_ND';
  if(r.includes('by-nd')) return 'CC_BY_ND';
  if(r.includes('by-nc')) return 'CC_BY_NC';
  if(r.includes('by')) return 'CC_BY';
  if(r.includes('public')) return 'PUBLIC_DOMAIN';
  return 'UNKNOWN';
}
export class OpenBeeldenProvider implements VideoProvider{
  providerName='open_beelden';
  async search(q:string):Promise<VideoCandidate[]>{
    const url=`${OAI}?verb=ListRecords&metadataPrefix=oai_oi&set=beeldengeluid&q=${encodeURIComponent(q)}`;
    return [{ externalId: url, title:`OAI search: ${q}`, provider:this.providerName }];
  }
  async getVideo(id:string):Promise<VideoMetadata>{
    const res=await fetch(`${OAI}?verb=GetRecord&identifier=${encodeURIComponent(id)}&metadataPrefix=oai_oi`);
    const xml=await res.text();
    const m=(re:RegExp)=> (xml.match(re)?.[1]||'').trim();
    const title=m(/<dc:title[^>]*>([^<]+)<\/dc:title>/);
    const desc=m(/<dc:description[^>]*>([^<]+)<\/dc:description>/);
    const lang=m(/<dc:language[^>]*>([^<]+)<\/dc:language>/);
    const rights=m(/<dc:rights[^>]*>([^<]+)<\/dc:rights>/);
    const src=m(/<oai_oi:file[^>]*>([^<]+)<\/oai_oi:file>/)||m(/<file[^>]*>([^<]+)<\/file>/);
    return { externalId:id, title: title||id, description:desc, language:lang||'nl', thumbnailUrl:`https://www.openbeelden.nl/images/${id}`, sourceUrl:src, embedUrl:`https://www.openbeelden.nl/media/${id}`, license:rights, licenseUrl:'https://creativecommons.org/licenses/by-sa/3.0/', attribution:'Beeld en Geluid / Open Beelden' };
  }
  async getRights(id:string):Promise<RightsMetadata>{
    const v=await this.getVideo(id);
    return { status: mapRights(v.license||''), license:v.license, licenseUrl:v.licenseUrl, attribution:v.attribution, termsUrl:'https://www.openbeelden.nl/about', checkedAt:new Date().toISOString() };
  }
  async getPlaybackSource(id:string):Promise<PlaybackSource>{
    const v=await this.getVideo(id);
    const isHls=v.sourceUrl.endsWith('.m3u8');
    return { type: isHls?'hls':'mp4', url: v.sourceUrl, embedUrl: v.embedUrl };
  }
  async supportsEmbedding(){ return true; }
  async supportsTimestampPlayback(){ return true; }
  createPlayer(_id:string, el:HTMLElement):PlayerAdapter{ return new HTML5Player(el); }
}
