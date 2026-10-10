import { photos } from '../assets/photos';
import { useBusiness } from '../business';

export default function Photo({ name, priority = false, className = '' }) {
  const { lang } = useBusiness();
  const photo = photos[name];
  return <img src={photo.src} width={photo.width} height={photo.height}
    alt={photo.alt[lang]} className={className}
    loading={priority ? 'eager' : 'lazy'} decoding="async"
    fetchpriority={priority ? 'high' : undefined} />;
}
