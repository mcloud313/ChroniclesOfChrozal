-- Dumped from database version 14.19 (Ubuntu 14.19-0ubuntu0.22.04.1)
-- Dumped by pg_dump version 14.19 (Ubuntu 14.19-0ubuntu0.22.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ability_templates; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.ability_templates (
    id integer NOT NULL,
    internal_name text NOT NULL,
    name text NOT NULL,
    ability_type text NOT NULL,
    class_req jsonb DEFAULT '[]'::jsonb,
    level_req integer DEFAULT 1,
    cost integer DEFAULT 0,
    target_type text,
    effect_type text,
    effect_details jsonb DEFAULT '{}'::jsonb,
    cast_time real DEFAULT 0.0,
    roundtime real DEFAULT 1.0,
    messages jsonb DEFAULT '{}'::jsonb,
    description text
);


ALTER TABLE public.ability_templates OWNER TO chrozal;

--
-- Name: ability_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.ability_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.ability_templates_id_seq OWNER TO chrozal;

--
-- Name: ability_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.ability_templates_id_seq OWNED BY public.ability_templates.id;


--
-- Name: areas; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.areas (
    id integer NOT NULL,
    name text NOT NULL,
    description text DEFAULT 'An undescribed area.'::text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.areas OWNER TO chrozal;

--
-- Name: areas_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.areas_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.areas_id_seq OWNER TO chrozal;

--
-- Name: areas_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.areas_id_seq OWNED BY public.areas.id;


--
-- Name: bank_accounts; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.bank_accounts (
    character_id integer NOT NULL,
    balance bigint DEFAULT 0 NOT NULL
);


ALTER TABLE public.bank_accounts OWNER TO chrozal;

--
-- Name: banked_items; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.banked_items (
    id integer NOT NULL,
    character_id integer NOT NULL,
    item_instance_id uuid NOT NULL,
    stored_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.banked_items OWNER TO chrozal;

--
-- Name: banked_items_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.banked_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.banked_items_id_seq OWNER TO chrozal;

--
-- Name: banked_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.banked_items_id_seq OWNED BY public.banked_items.id;


--
-- Name: characters; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.characters (
    id integer NOT NULL,
    player_id integer NOT NULL,
    first_name text NOT NULL,
    last_name text NOT NULL,
    sex text NOT NULL,
    race_id integer,
    class_id integer,
    level integer DEFAULT 1,
    description text DEFAULT ''::text,
    hp real DEFAULT 50.0,
    max_hp real DEFAULT 50.0,
    essence real DEFAULT 20.0,
    max_essence real DEFAULT 20.0,
    spiritual_tether integer,
    xp_pool real DEFAULT 0.0,
    xp_total real DEFAULT 0.0,
    status text DEFAULT 'ALIVE'::text NOT NULL,
    stance text DEFAULT 'Standing'::text NOT NULL,
    unspent_skill_points integer DEFAULT 0 NOT NULL,
    unspent_attribute_points integer DEFAULT 0 NOT NULL,
    stats jsonb DEFAULT '{}'::jsonb,
    skills jsonb DEFAULT '{}'::jsonb,
    known_spells jsonb DEFAULT '[]'::jsonb,
    known_abilities jsonb DEFAULT '[]'::jsonb,
    location_id integer DEFAULT 1,
    inventory jsonb DEFAULT '[]'::jsonb,
    equipment jsonb DEFAULT '{}'::jsonb,
    coinage integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_saved timestamp with time zone,
    total_playtime_seconds integer DEFAULT 0 NOT NULL
);


ALTER TABLE public.characters OWNER TO chrozal;

--
-- Name: characters_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.characters_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.characters_id_seq OWNER TO chrozal;

--
-- Name: characters_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.characters_id_seq OWNED BY public.characters.id;


--
-- Name: classes; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.classes (
    id integer NOT NULL,
    name text NOT NULL,
    description text
);


ALTER TABLE public.classes OWNER TO chrozal;

--
-- Name: classes_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.classes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.classes_id_seq OWNER TO chrozal;

--
-- Name: classes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.classes_id_seq OWNED BY public.classes.id;


--
-- Name: game_economy; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.game_economy (
    key text NOT NULL,
    value bigint DEFAULT 0 NOT NULL
);


ALTER TABLE public.game_economy OWNER TO chrozal;

--
-- Name: item_instances; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.item_instances (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    template_id integer NOT NULL,
    owner_char_id integer,
    room_id integer,
    container_id uuid,
    condition integer DEFAULT 100 NOT NULL,
    instance_stats jsonb DEFAULT '{}'::jsonb,
    CONSTRAINT single_location_check CHECK ((((owner_char_id IS NOT NULL) AND (room_id IS NULL) AND (container_id IS NULL)) OR ((owner_char_id IS NULL) AND (room_id IS NOT NULL) AND (container_id IS NULL)) OR ((owner_char_id IS NULL) AND (room_id IS NULL) AND (container_id IS NOT NULL))))
);


ALTER TABLE public.item_instances OWNER TO chrozal;

--
-- Name: item_templates; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.item_templates (
    id integer NOT NULL,
    name text NOT NULL,
    description text DEFAULT 'An ordinary item.'::text,
    type text NOT NULL,
    stats jsonb DEFAULT '{}'::jsonb,
    flags jsonb DEFAULT '[]'::jsonb,
    damage_type text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.item_templates OWNER TO chrozal;

--
-- Name: item_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.item_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.item_templates_id_seq OWNER TO chrozal;

--
-- Name: item_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.item_templates_id_seq OWNED BY public.item_templates.id;


--
-- Name: mob_templates; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.mob_templates (
    id integer NOT NULL,
    name text NOT NULL,
    description text DEFAULT 'A creature.'::text,
    mob_type text,
    level integer DEFAULT 1 NOT NULL,
    stats jsonb DEFAULT '{}'::jsonb,
    max_hp integer DEFAULT 10 NOT NULL,
    attacks jsonb DEFAULT '[]'::jsonb,
    loot jsonb DEFAULT '{}'::jsonb,
    flags jsonb DEFAULT '[]'::jsonb,
    respawn_delay_seconds integer DEFAULT 300,
    variance jsonb DEFAULT '{}'::jsonb,
    movement_chance real DEFAULT 0.0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.mob_templates OWNER TO chrozal;

--
-- Name: mob_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.mob_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.mob_templates_id_seq OWNER TO chrozal;

--
-- Name: mob_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.mob_templates_id_seq OWNED BY public.mob_templates.id;


--
-- Name: players; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.players (
    id integer NOT NULL,
    username text NOT NULL,
    hashed_password text NOT NULL,
    email text NOT NULL,
    is_admin boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_login timestamp with time zone
);


ALTER TABLE public.players OWNER TO chrozal;

--
-- Name: players_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.players_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.players_id_seq OWNER TO chrozal;

--
-- Name: players_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.players_id_seq OWNED BY public.players.id;


--
-- Name: races; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.races (
    id integer NOT NULL,
    name text NOT NULL,
    description text
);


ALTER TABLE public.races OWNER TO chrozal;

--
-- Name: races_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.races_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.races_id_seq OWNER TO chrozal;

--
-- Name: races_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.races_id_seq OWNED BY public.races.id;


--
-- Name: room_objects; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.room_objects (
    id integer NOT NULL,
    room_id integer NOT NULL,
    name text NOT NULL,
    description text DEFAULT 'It looks unremarkable.'::text,
    keywords jsonb DEFAULT '[]'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.room_objects OWNER TO chrozal;

--
-- Name: room_objects_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.room_objects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.room_objects_id_seq OWNER TO chrozal;

--
-- Name: room_objects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.room_objects_id_seq OWNED BY public.room_objects.id;


--
-- Name: rooms; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.rooms (
    id integer NOT NULL,
    area_id integer NOT NULL,
    name text NOT NULL,
    description text DEFAULT 'You see nothing special.'::text,
    exits jsonb DEFAULT '{}'::jsonb,
    flags jsonb DEFAULT '[]'::jsonb,
    spawners jsonb DEFAULT '{}'::jsonb,
    coinage integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.rooms OWNER TO chrozal;

--
-- Name: rooms_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.rooms_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.rooms_id_seq OWNER TO chrozal;

--
-- Name: rooms_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.rooms_id_seq OWNED BY public.rooms.id;


--
-- Name: shop_inventories; Type: TABLE; Schema: public; Owner: chrozal
--

CREATE TABLE public.shop_inventories (
    id integer NOT NULL,
    room_id integer NOT NULL,
    item_template_id integer NOT NULL,
    stock_quantity integer DEFAULT '-1'::integer NOT NULL,
    buy_price_modifier real DEFAULT 1.25 NOT NULL,
    sell_price_modifier real DEFAULT 0.75 NOT NULL
);


ALTER TABLE public.shop_inventories OWNER TO chrozal;

--
-- Name: shop_inventories_id_seq; Type: SEQUENCE; Schema: public; Owner: chrozal
--

CREATE SEQUENCE public.shop_inventories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.shop_inventories_id_seq OWNER TO chrozal;

--
-- Name: shop_inventories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: chrozal
--

ALTER SEQUENCE public.shop_inventories_id_seq OWNED BY public.shop_inventories.id;


--
-- Name: ability_templates id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.ability_templates ALTER COLUMN id SET DEFAULT nextval('public.ability_templates_id_seq'::regclass);


--
-- Name: areas id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.areas ALTER COLUMN id SET DEFAULT nextval('public.areas_id_seq'::regclass);


--
-- Name: banked_items id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.banked_items ALTER COLUMN id SET DEFAULT nextval('public.banked_items_id_seq'::regclass);


--
-- Name: characters id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.characters ALTER COLUMN id SET DEFAULT nextval('public.characters_id_seq'::regclass);


--
-- Name: classes id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.classes ALTER COLUMN id SET DEFAULT nextval('public.classes_id_seq'::regclass);


--
-- Name: item_templates id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.item_templates ALTER COLUMN id SET DEFAULT nextval('public.item_templates_id_seq'::regclass);


--
-- Name: mob_templates id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.mob_templates ALTER COLUMN id SET DEFAULT nextval('public.mob_templates_id_seq'::regclass);


--
-- Name: players id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.players ALTER COLUMN id SET DEFAULT nextval('public.players_id_seq'::regclass);


--
-- Name: races id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.races ALTER COLUMN id SET DEFAULT nextval('public.races_id_seq'::regclass);


--
-- Name: room_objects id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.room_objects ALTER COLUMN id SET DEFAULT nextval('public.room_objects_id_seq'::regclass);


--
-- Name: rooms id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.rooms ALTER COLUMN id SET DEFAULT nextval('public.rooms_id_seq'::regclass);


--
-- Name: shop_inventories id; Type: DEFAULT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.shop_inventories ALTER COLUMN id SET DEFAULT nextval('public.shop_inventories_id_seq'::regclass);


--
-- Name: ability_templates ability_templates_internal_name_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.ability_templates
    ADD CONSTRAINT ability_templates_internal_name_key UNIQUE (internal_name);


--
-- Name: ability_templates ability_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.ability_templates
    ADD CONSTRAINT ability_templates_pkey PRIMARY KEY (id);


--
-- Name: areas areas_name_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.areas
    ADD CONSTRAINT areas_name_key UNIQUE (name);


--
-- Name: areas areas_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.areas
    ADD CONSTRAINT areas_pkey PRIMARY KEY (id);


--
-- Name: bank_accounts bank_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.bank_accounts
    ADD CONSTRAINT bank_accounts_pkey PRIMARY KEY (character_id);


--
-- Name: banked_items banked_items_item_instance_id_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.banked_items
    ADD CONSTRAINT banked_items_item_instance_id_key UNIQUE (item_instance_id);


--
-- Name: banked_items banked_items_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.banked_items
    ADD CONSTRAINT banked_items_pkey PRIMARY KEY (id);


--
-- Name: characters characters_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.characters
    ADD CONSTRAINT characters_pkey PRIMARY KEY (id);


--
-- Name: characters characters_player_id_first_name_last_name_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.characters
    ADD CONSTRAINT characters_player_id_first_name_last_name_key UNIQUE (player_id, first_name, last_name);


--
-- Name: classes classes_name_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.classes
    ADD CONSTRAINT classes_name_key UNIQUE (name);


--
-- Name: classes classes_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.classes
    ADD CONSTRAINT classes_pkey PRIMARY KEY (id);


--
-- Name: game_economy game_economy_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.game_economy
    ADD CONSTRAINT game_economy_pkey PRIMARY KEY (key);


--
-- Name: item_instances item_instances_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.item_instances
    ADD CONSTRAINT item_instances_pkey PRIMARY KEY (id);


--
-- Name: item_templates item_templates_name_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.item_templates
    ADD CONSTRAINT item_templates_name_key UNIQUE (name);


--
-- Name: item_templates item_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.item_templates
    ADD CONSTRAINT item_templates_pkey PRIMARY KEY (id);


--
-- Name: mob_templates mob_templates_name_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.mob_templates
    ADD CONSTRAINT mob_templates_name_key UNIQUE (name);


--
-- Name: mob_templates mob_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.mob_templates
    ADD CONSTRAINT mob_templates_pkey PRIMARY KEY (id);


--
-- Name: players players_email_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.players
    ADD CONSTRAINT players_email_key UNIQUE (email);


--
-- Name: players players_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.players
    ADD CONSTRAINT players_pkey PRIMARY KEY (id);


--
-- Name: players players_username_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.players
    ADD CONSTRAINT players_username_key UNIQUE (username);


--
-- Name: races races_name_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.races
    ADD CONSTRAINT races_name_key UNIQUE (name);


--
-- Name: races races_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.races
    ADD CONSTRAINT races_pkey PRIMARY KEY (id);


--
-- Name: room_objects room_objects_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.room_objects
    ADD CONSTRAINT room_objects_pkey PRIMARY KEY (id);


--
-- Name: room_objects room_objects_room_id_name_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.room_objects
    ADD CONSTRAINT room_objects_room_id_name_key UNIQUE (room_id, name);


--
-- Name: rooms rooms_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_pkey PRIMARY KEY (id);


--
-- Name: shop_inventories shop_inventories_pkey; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.shop_inventories
    ADD CONSTRAINT shop_inventories_pkey PRIMARY KEY (id);


--
-- Name: shop_inventories shop_inventories_room_id_item_template_id_key; Type: CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.shop_inventories
    ADD CONSTRAINT shop_inventories_room_id_item_template_id_key UNIQUE (room_id, item_template_id);


--
-- Name: bank_accounts bank_accounts_character_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.bank_accounts
    ADD CONSTRAINT bank_accounts_character_id_fkey FOREIGN KEY (character_id) REFERENCES public.characters(id) ON DELETE CASCADE;


--
-- Name: banked_items banked_items_character_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.banked_items
    ADD CONSTRAINT banked_items_character_id_fkey FOREIGN KEY (character_id) REFERENCES public.characters(id) ON DELETE CASCADE;


--
-- Name: banked_items banked_items_item_instance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.banked_items
    ADD CONSTRAINT banked_items_item_instance_id_fkey FOREIGN KEY (item_instance_id) REFERENCES public.item_instances(id) ON DELETE CASCADE;


--
-- Name: characters characters_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.characters
    ADD CONSTRAINT characters_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.classes(id) ON DELETE SET NULL;


--
-- Name: characters characters_player_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.characters
    ADD CONSTRAINT characters_player_id_fkey FOREIGN KEY (player_id) REFERENCES public.players(id) ON DELETE CASCADE;


--
-- Name: characters characters_race_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.characters
    ADD CONSTRAINT characters_race_id_fkey FOREIGN KEY (race_id) REFERENCES public.races(id) ON DELETE SET NULL;


--
-- Name: item_instances item_instances_container_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.item_instances
    ADD CONSTRAINT item_instances_container_id_fkey FOREIGN KEY (container_id) REFERENCES public.item_instances(id) ON DELETE SET NULL;


--
-- Name: item_instances item_instances_owner_char_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.item_instances
    ADD CONSTRAINT item_instances_owner_char_id_fkey FOREIGN KEY (owner_char_id) REFERENCES public.characters(id) ON DELETE SET NULL;


--
-- Name: item_instances item_instances_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.item_instances
    ADD CONSTRAINT item_instances_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(id) ON DELETE SET NULL;


--
-- Name: item_instances item_instances_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.item_instances
    ADD CONSTRAINT item_instances_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.item_templates(id) ON DELETE CASCADE;


--
-- Name: room_objects room_objects_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.room_objects
    ADD CONSTRAINT room_objects_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(id) ON DELETE CASCADE;


--
-- Name: rooms rooms_area_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_area_id_fkey FOREIGN KEY (area_id) REFERENCES public.areas(id) ON DELETE RESTRICT;


--
-- Name: shop_inventories shop_inventories_item_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.shop_inventories
    ADD CONSTRAINT shop_inventories_item_template_id_fkey FOREIGN KEY (item_template_id) REFERENCES public.item_templates(id) ON DELETE CASCADE;


--
-- Name: shop_inventories shop_inventories_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chrozal
--

ALTER TABLE ONLY public.shop_inventories
    ADD CONSTRAINT shop_inventories_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(id) ON DELETE CASCADE;

