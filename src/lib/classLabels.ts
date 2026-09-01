import type { ClassCatalogItem } from '../types/muravei';

/** Common military class RU labels (YAML has EN-only names). */
const RU_BY_EN: Record<string, string> = {
  tank: 'Танк',
  soldier: 'Солдат',
  person_in_camouflage_uniform: 'Боец в камуфляже',
  armed_person: 'Вооружённый человек',
  group_of_soldiers: 'Группа солдат',
  military_truck: 'Военный грузовик',
  tanker_truck: 'Топливозаправщик',
  military_jeep: 'Военный джип',
  armored_vehicle: 'Бронетехника',
  armored_personnel_carrier: 'БТР',
  howitzer: 'Гаубица',
  artillery: 'Артиллерия',
  quadcopter_drone: 'Квадрокоптер',
  fpv_drone: 'FPV-дрон',
  uav: 'БПЛА',
  trench: 'Окоп',
  bunker: 'Бункер',
  barbed_wire: 'Колючая проволока',
  anti_tank_mine: 'ПТМ',
  anti_personnel_mine: 'ПМ',
  anti_tank_ditch: 'Противотанковый ров',
  camouflage_net: 'Маскировочная сеть',
  foxhole: 'Окоп (foxhole)',
  litter_pile: 'Мусорная куча',
  dug_in_artillery: 'Закопанная артиллерия',
  spoil_heap_of_dug_out_soil: 'Отвал вынутого грунта',
  mine: 'Мина',
  unknown: 'Неизвестно',
};

function normalizeClassKey(className: string): string {
  return (className || '').trim().toLowerCase().replace(/-/g, ' ').replace(/\s+/g, '_');
}

export function classLabelRu(
  classId: number | undefined,
  className: string,
  catalog: ClassCatalogItem[],
): string {
  const item = classId != null ? catalog.find((c) => c.id === classId) : undefined;
  if (item?.name_ru?.trim()) return item.name_ru.trim();
  const key = normalizeClassKey(className);
  const byName = catalog.find(
    (c) => c.name_en === key || normalizeClassKey(c.name_raw) === key,
  );
  if (byName?.name_ru?.trim()) return byName.name_ru.trim();
  if (RU_BY_EN[key]) return RU_BY_EN[key];
  return (className || '').replace(/_/g, ' ');
}

export function classDisplayLine(
  classId: number | undefined,
  className: string,
  catalog: ClassCatalogItem[],
): string {
  const ru = classLabelRu(classId, className, catalog);
  const en = (className || '').replace(/_/g, ' ');
  if (ru.toLowerCase() === en.toLowerCase()) return ru;
  return `${ru} (${en})`;
}
