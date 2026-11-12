"""Synthetic connection views materialized from authored log observations.

These are convenience views, not independent corroborating sources. No credentials
or tokens are generated or refreshed by these inspection tools.
"""
import hashlib


def materialize(sources):
    connections={}
    refresh=[]
    for row in sources.get('logs',[]):
        if not any(key in row for key in ('connection_id','connection_status','granted_scopes','refresh_status')):
            continue
        identity=row.get('connection_id') or f"{row.get('service','unknown')}:{row.get('tenant','shared')}"
        digest=hashlib.sha256((identity+':'+str(row.get('record_id',''))).encode()).hexdigest()[:12]
        current=connections.setdefault(identity,{
            'record_id':'connection-view-'+digest,'connection_id':identity,
            'service':row.get('service'),'tenant':row.get('tenant'),
            'connection_status':'not_recorded','granted_scopes':None,'token_state':'not_recorded',
            'source_kind':'derived_view','derived_from':[]})
        if 'record_id' in row:
            current['derived_from'].append(row['record_id'])
        for key in ('connection_status','granted_scopes'):
            if key in row:
                current[key]=row[key]
        if row.get('credential_cache')=='expired':
            current['token_state']='expired'
        if 'refresh_status' in row:
            status=row['refresh_status']
            refresh.append({'record_id':'refresh-view-'+str(row['record_id']),
                'connection_id':identity,'service':row.get('service'),'tenant':row.get('tenant'),
                'timestamp':row.get('timestamp'),'refresh_status':status,'connection_status':row.get('connection_status'),
                'credential_cache':row.get('credential_cache'),
                'source_kind':'derived_view','derived_from':[row['record_id']]})
    return {'connections':list(connections.values()),'refresh_history':refresh}
