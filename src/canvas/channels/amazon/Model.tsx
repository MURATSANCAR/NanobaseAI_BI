import ModelPage from '../marketplace/ModelPage';
import { AmazonFrame } from './parts';

/** Aşama 0: Amazon TR satış modeli Logo'dan ölçülür (tahmin yok). */
export default function AmazonModel() {
  return <ModelPage platform="amazon" Frame={AmazonFrame} />;
}
