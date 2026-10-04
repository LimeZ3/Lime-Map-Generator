import { createContext, useContext } from 'react';
import { translate } from './i18n';
import type { Language } from './i18n';
export const LanguageContext=createContext<Language>('en');
export function useTranslation(){
  const language=useContext(LanguageContext);
  return (text:string)=>translate(language,text);
}
