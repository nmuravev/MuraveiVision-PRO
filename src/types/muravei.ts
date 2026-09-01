// src/types/muravei.ts
// Военные классы из military_classes.yaml (238 классов)
export type MilitaryClass = 
| 'tank' | 'tank_turret_in_ground' | 'dug_in_artillery'
| 'armored_vehicle' | 'armored_personnel_carrier'
| 'vehicle_with_cage_armor' | 'military_truck' | 'military_jeep'
| 'tanker_truck' | 'self_propelled_artillery'
| 'multiple_rocket_launcher' | 'anti_aircraft_gun'
| 'howitzer' | 'missile_launcher'
| 'military_helicopter' | 'military_aircraft'
| 'quadcopter_drone' | 'military_boat'
| 'inflatable_decoy' | 'soldier'
| 'person_in_camouflage_uniform' | 'armed_person'
| 'person_carrying_rifle' | 'person_with_shovel'
| 'soldier_digging_trench' | 'group_of_soldiers'
| 'rifle' | 'machine_gun' | 'grenade_launcher'
| 'anti_tank_missile' | 'ammunition_box'
| 'wooden_crate' | 'metal_barrel' | 'jerry_can'
| 'portable_generator' | 'field_kitchen'
| 'wooden_pallet' | 'military_radio_antenna'
| 'radio_mast' | 'satellite_dish' | 'radar'
| 'electronic_warfare_antenna' | 'communication_antenna'
| 'trench' | 'bunker' | 'dugout_entrance'
| 'foxhole' | 'barbed_wire' | 'barbed_wire_coil'
| 'anti_tank_obstacle' | 'dragon_teeth_obstacle'
| 'czech_hedgehog_obstacle' | 'concrete_block_barricade'
| 'gabion_barrier' | 'sandbag_wall' | 'checkpoint'
| 'watchtower' | 'earth_berm' | 'anti_tank_ditch'
| 'camouflage_net' | 'camouflaged_position'
| 'vehicle_under_net' | 'covered_vehicle'
| 'military_tent' | 'medical_tent' | 'command_tent'
| 'anti_drone_net' | 'drone_protection_cage'
| 'metal_grille_armor' | 'cut_branches_on_ground'
| 'plastic_bottle' | 'metal_can' | 'food_wrapper'
| 'discarded_paper' | 'cardboard_box' | 'plastic_bag'
| 'garbage_pile' | 'campfire_remains' | 'smoke_plume'
| 'dust_cloud' | 'tire_track' | 'footpath_in_grass'
| 'trampled_vegetation' | 'disturbed_soil'
| 'fresh_dug_dirt' | 'discarded_clothing'
| 'soldier_in_civilian_clothing' | 'soldier_lying_prone'
| 'running_soldier' | 'soldier_carrying_military_backpack'
| 'combat_medic_with_armband' | 'wounded_soldier'
| 'fallen_body' | 'ghillie_suit' | 'military_helmet'
| 'body_armor_vest' | 'tactical_vest_with_pouches'
| 'military_backpack' | 'combat_tourniquet'
| 'rolled_bandage' | 'bloody_bandage'
| 'first_aid_pouch_ifak' | 'stretcher'
| 'battle_rifle' | 'carbine' | 'submachine_gun'
| 'light_machine_gun' | 'general_purpose_machine_gun'
| 'heavy_machine_gun' | 'anti_materiel_rifle'
| 'suppressed_rifle' | 'underbarrel_grenade_launcher'
| 'telescopic_sight' | 'bipod' | 'spent_cartridge_case'
| 'pile_of_shell_casings' | 'spent_artillery_shell_casing'
| 'pile_of_artillery_shell_casings'
| 'spent_mortar_round_tail_fin' | 'ammunition_magazine'
| 'ammo_belt' | 'linked_ammunition_box'
| 'ammunition_crate' | 'artillery_shell'
| 'mortar_round' | 'hand_grenade' | 'anti_tank_mine'
| 'anti_personnel_mine' | 'directional_fragmentation_mine'
| 'bounding_mine' | 'tripwire_booby_trap'
| 'rpg7_grenade_launcher' | 'spent_rpg_launch_tube'
| 'rpg18_mukha_launcher' | 'rpg26_launcher'
| 'm72_law_launcher' | 'at4_disposable_launcher'
| 'mro_a_shmel_thermobaric' | 'anti_tank_guided_missile_launcher'
| 'atgm_missile_in_container' | 'manpads'
| 'fpv_drone' | 'fixed_wing_drone'
| 'reconnaissance_drone' | 'drone_propeller'
| 'drone_wreckage' | 'fiber_optic_spool'
| 'thin_glinting_fiber_optic_cable' | 'drone_antenna'
| 'drone_controller_with_screen' | 'field_radio_station'
| 'whip_antenna' | 'radar_station' | 'satellite_dish_antenna'
| 'gasoline_generator' | 'laptop_computer'
| 'freshly_dug_soil_patch' | 'spoil_heap_of_dug_out_soil'
| 'dugout_ventilation_pipe' | 'shell_crater_with_scorched_earth'
| 'shrapnel_fragments' | 'pile_of_cut_branches'
| 'wilted_cut_foliage' | 'narrow_footpath_through_bushes'
| 'trampled_flattened_grass' | 'extinguished_campfire_site'
| 'grey_ash_soot_patch' | 'muzzle_blast_scorched_grass'
| 'disturbed_snow_with_tracks' | 'dark_melt_spots_on_snow'
| 'sun_glint_on_optics_or_metal' | 'white_plastic_sheet_or_bag'
| 'cigarette_pack' | 'food_can' | 'litter_pile'
| 'jerry_can_fuel_container' | 'discarded_tire'
| 'pile_of_cement_bags' | 'sand_or_gravel_pile'
| 'rebar_steel_rods_bundle' | 'welded_wire_mesh'
| 'roofing_felt_rolls' | 'construction_debris_pile'
| 'military_motorcycle' | 'atv_quad_bike' | 'snowmobile'
| 'pickup_truck_with_mounted_gun' | 'fuel_bowser_truck'
| 'ambulance_vehicle' | 'evacuation_vehicle'
| 'towed_howitzer' | 'mortar' | 'mortar_baseplate'
| 'automatic_grenade_launcher' | 'heavy_machine_gun_on_tripod'
| 'train_car_with_cargo' | 'armored_vehicle_on_flatbed'
| 'tarp_covered_vehicle_on_train_platform'
| 'stack_of_railway_sleepers' | 'field_bakery_with_smoking_chimney'
| 'medical_tent_cluster' | 'dummy_tank_decoy'
| 'dummy_artillery_piece' | 'corner_radar_reflector'
| 'smoke_canister' | 'wood_burning_field_stove'
| 'thermal_imaging_camera' | 'night_vision_goggles'
| 'flare_gun' | 'signal_flare' | 'field_telephone'
| 'communication_cable_reel' | 'mobile_command_post'
| 'field_communications_van' | 'electronic_warfare_vehicle'
| 'jamming_equipment' | 'mine_detector'
| 'explosive_ordnance_disposal_robot' | 'military_working_dog'
| 'handler_with_military_dog' | 'field_hospital'
| 'mobile_surgery_unit' | 'supply_depot'
| 'ammunition_storage_facility' | 'fuel_storage_tank'
| 'military_convoy' | 'patrol_route' | 'observation_post'
| 'listening_post' | 'forward_operating_base'
| 'combat_outpost' | 'vehicle_maintenance_area'
| 'refueling_station' | 'ammunition_reloading_point'
| 'casualty_collection_point' | 'prisoner_of_war_holding_area'
| 'military_checkpoint_barrier' | 'military_guard_shack';

// Bounding box детекции
export interface BoundingBox {
  x1: number; // normalized 0..1
  y1: number;
  x2: number;
  y2: number;
}

export interface MotionVector {
  vx: number;
  vy: number;
  speed: number;
  ego_vx?: number;
  ego_vy?: number;
}

// Объект детекции
export interface DetectedObject {
  id: string;
  class_ru: string;
  class_en: string;
  confidence: number;
  bbox: BoundingBox;
  color?: string;
  notes?: string;
  class_id?: number;
  is_edited?: boolean;
  origin?: 'auto' | 'manual' | 'batch_scan';
  crop_path?: string;
  source_video?: string;
  time_sec?: number;
  track_id?: number | string;
  motion?: MotionVector;
  /** Original YOLO class before operator override */
  ai_class_name?: string | null;
}

export interface PersistedDetection {
  id: string;
  created_at: number;
  source_video: string;
  time_sec: number;
  frame_idx: number;
  class_id: number;
  class_name: string;
  ai_class_name?: string | null;
  confidence: number;
  bbox_x: number;
  bbox_y: number;
  bbox_w: number;
  bbox_h: number;
  crop_path?: string | null;
  is_edited: boolean;
  edited_by?: string | null;
  edited_at?: number | null;
  user_notes: string;
  is_deleted: boolean;
  origin: 'auto' | 'manual' | string;
  gps_lat?: number | null;
  gps_lon?: number | null;
  gps_alt?: number | null;
}

export interface ClassCatalogItem {
  id: number;
  name_raw: string;
  name_en: string;
  name_ru?: string;
  aliases?: string[];
  enabled?: boolean;
  in_prompt?: boolean;
  confidence_threshold?: number | null;
  has_override?: boolean;
  is_model_class?: boolean;
}

// Момент детекции (привязан к таймкоду)
export interface DetectionMoment {
  id: string;
  timestamp: string; // "0:00:13"
  timeSec: number;
  frameIdx: number;
  objects: DetectedObject[];
  imageUrl?: string;
  cropAnalysis?: string;
  isFlagged?: boolean;
}

// Конфигурация анализа
export interface AnalysisConfig {
  droneMode: boolean;
  frameStep: number; // 15 или 30
  confidenceThreshold: number; // 0.15 .. 0.90
  modelName: string;
  useFinetuned: boolean;
  aiAnalystEnabled: boolean;
  cpuThreadsLimit?: number;
  enableLowResourceMode?: boolean;
}

// Характеристики железа
export interface HardwareSpecs {
  cpu: string;
  gpu: string;
  vramMb: number;
  cudaAvailable: boolean;
  providers: string[];
  activeModel: string;
}

// Режимы просмотра
export type ViewMode = 
| 'mini' 
| 'pro' 
| 'training' 
| 'merge' 
| 'gallery' 
| 'report' 
| 'diagnostics' 
| 'portable';

// Тема оформления
export type UiTheme = 'premiere' | 'cyber-neon';

// Роль пользователя
export type UserRole = 'operator' | 'engineer' | 'master';

// Запись лога
export interface LogEntry {
  id: string;
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG';
  message: string;
  source?: string;
}