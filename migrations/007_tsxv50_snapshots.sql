create table public.tsxv50_snapshots (
    id         bigserial    primary key,
    symbols    jsonb        not null,
    created_at timestamptz  not null default now()
);

-- Seed with current watchlist from top50config.json
insert into public.tsxv50_snapshots (symbols) values (
  '["SCZ.V","UCU.V","MLP.V","AUMB.V","TDG.V","OMG.V","PPP.V","AGX.V","NCX.V","GGA.V","GSVR.V","SLVR.V","APGO.V","ITR.V","AGMR.V","FLT.V","BYN.V","FMT.V","HSTR.V","ONYX.V","AHR.V","CERT.V","WGO.V","TAU.V","BRC.V","GG.V","GQC.V","CAPT.V","SSV.V","AGAG.V","SAG.V","GGO.V","AMX.V","QNC.V","WPG.V","SLI.V","MMY.V","NAU.V","THX.V","LUCA.V","VIPR.V","NEXG.V","SM.V","GSI.V","KTO.V","BZ.V","CKG.V","ROCK.V","OMI.V","VROY.V","AGA.V"]'
);
