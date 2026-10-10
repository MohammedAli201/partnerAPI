import city from './photos/city.avif';
import mobileHand from './photos/mobile-hand.avif';
import mobileUser from './photos/mobile-user.avif';
import money from './photos/money.avif';
import phone from './photos/phone.avif';

// User-supplied photos. Descriptions do not imply an office, app or live service.
export const photos = {
  city: { src: city, width: 1000, height: 667, alt: {
    en: 'City buildings beneath a cloudy sky.',
    so: 'Dhismayaal magaalo oo cir daruuro leh ka hooseeya.',
  } },
  mobileHand: { src: mobileHand, width: 1000, height: 563, alt: {
    en: 'Hands using a smartphone with an illustrative screen.',
    so: 'Gacmo isticmaalaya telefoon casri ah oo shaashad tusaale ah leh.',
  } },
  mobileUser: { src: mobileUser, width: 900, height: 600, alt: {
    en: 'A person looking at a mobile phone.',
    so: 'Qof eegaya telefoonka gacanta.',
  } },
  money: { src: money, width: 900, height: 600, alt: {
    en: 'Hands counting US dollar banknotes.',
    so: 'Gacmo tirinaya lacagta doolarka Mareykanka.',
  } },
  phone: { src: phone, width: 800, height: 534, alt: {
    en: 'A smartphone standing against a dark background.',
    so: 'Telefoon casri ah oo taagan meel madow.',
  } },
};
