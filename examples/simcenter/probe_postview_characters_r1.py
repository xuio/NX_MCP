def run(executor):
    session=executor.session
    sim=session.Parts.BaseWork
    if not sim.FullPath.endswith('public_40c_r1.sim'):
        raise ValueError('Requires isolated public 40 C case')
    post=session.Post
    view=post.GetMainPostviewIdInActivePart()
    rows=[]
    try:
        for name in ('Test 15 mm','Test-15 mm','Test:15 mm','Test_15 mm','Baldower ideal spreader 1_5 mm - 1 mm mesh'):
            try:
                post.PostviewRename(view,name)
                rows.append({'name':name,'length':len(name),'accepted':True})
            except Exception as error:
                rows.append({'name':name,'length':len(name),'accepted':False,'nx_code':getattr(error,'ErrorCode',None)})
    finally:
        post.PostviewRename(view,'Public40')
        sim.ModelingViews.WorkView.Fit()
        sim.ModelingViews.WorkView.UpdateDisplay()
    return {'rows':rows,'view':view,'owner':sim.FullPath,'restored_name':'Public40','solver_launched':False}
