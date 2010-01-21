from sqlalchemy import select, distinct, Table, Column, Integer, String
from sqlalchemy.sql.expression import case, func, and_, bindparam
from turbogears import controllers, identity, expose, url, database
from turbogears.database import session, metadata, mapper
from turbogears.widgets import DataGrid, AjaxGrid
from beaker.server.widgets import JobMatrixReport as JobMatrixWidget

import model

import logging
log = logging.getLogger(__name__)

class JobMatrix: 
    job_matrix_widget = JobMatrixWidget() 
    arches_used = {} 
    @expose(template='beaker.server.templates.generic')
    def index(self,**kw):    
        matrix_options = {} 
        jobs = model.Job.query().group_by([model.Job.whiteboard])
        new_whiteboard_options = [(job.whiteboard,job.whiteboard) for job in jobs]  
        matrix_options['whiteboard_options'] = new_whiteboard_options 
        #log.debug(kw)
        if ('job_ids' in kw) or ('whiteboard' in kw): 
            #log.debug('in if clause')
            gen_results = self.generate(**kw) 
            matrix_options['grid'] = gen_results['grid']
            matrix_options['list'] = gen_results['data'] 
            if 'whiteboard' in kw:
                matrix_options['job_ids_options'] = model.Job.by_whiteboard(kw['whiteboard'])  
        else: 
            pass         
        log.debug('Matrix options is %s ' % matrix_options)
        return dict(widget = self.job_matrix_widget,widget_options=matrix_options, title="Job Matrix Report")
     
    @classmethod
    def arch_stat_getter(cls,this_arch):
      #ahh nice little closure...
      def f(x):
          try:
              if x.arch == this_arch:    
                  return 'Pass:%s Fail:%s Warn:%s' % (x.Pass,x.Fail,x.Warn) 
              #return '%s' % x[0].Pass
          except Exception,(e):
             return 'opps exception %s' % e
      return f      

    @classmethod
    def _job_grid_fields(self,arches_used,**kw):
        fields = [] 
        fields.append(DataGrid.Column(name='task', getter=lambda x: x.task_name, title='Task')) 
        
        for arch in arches_used:
            fields.append(DataGrid.Column(name=arch, getter=JobMatrix.arch_stat_getter(arch), title=arch))
        return fields 
 
    
    def generate(self,**kw):
        grid_data = self.generate_data(**kw)
        arches_used = {}
        for grid in grid_data:
            arches_used[grid.arch] = 1
        grid = DataGrid(fields = self._job_grid_fields(arches_used.keys()))
        return {'grid' : grid, 'data' : grid_data }     
      
   
    def generate_data(self,**kw): 
        jobs = []
        whiteboard_data = {} 
        if 'job_ids' in kw:
            jobs = kw['job_ids'].split() 
        elif 'whiteboard' in kw:
            job_query = model.Job.query().filter(model.Job.whiteboard == kw['whiteboard'])
            for job in job_query:
                jobs.append(job.id) 
        else:
           pass
           #raise AssertionError('Incorrect or no filter passed to job matrix report generator')
        recipes = model.MachineRecipe.query().join(['distro','arch']).join(['recipeset','job']).add_column(model.Arch.arch) 
        #recipes = model.MachineRecipe.query().join(['distro','arch']).join(['recipeset','job']).filter(model.RecipeSet.job_id.in_(jobs)).add_column(model.Arch.arch) 
        #log.debug(recipes)
        for recipe,arch in recipes:     
            if arch != 'i386':
                log.debug('Found nont i386 arch %s' % arch)
            whiteboard_data[arch] = recipe.whiteboard 

        case0 = case([(model.task_result_table.c.result == 'New',1)],else_=0)
        case1 = case([(model.task_result_table.c.result == 'Pass',1)],else_=0)
        case2 = case([(model.task_result_table.c.result == 'Warn',1)],else_=0)
        case3 = case([(model.task_result_table.c.result == 'Fail',1)],else_=0)
        case4 = case([(model.task_result_table.c.result == 'Panic',1)],else_=0) 
    
        arch_alias = model.arch_table.alias()
        recipe_table_alias = model.recipe_table.alias()
        s2 = select([model.task_table.c.id.label('task_id'),
                     model.task_result_table.c.id.label('result'),
                     recipe_table_alias.c.whiteboard,
                     arch_alias.c.arch,
                     case0.label('rc0'),
                     case1.label('rc1'),
                     case2.label('rc2'),
                     case3.label('rc3'),
                     case4.label('rc4')],
                   
                     and_( model.recipe_set_table.c.job_id.in_(jobs),
                           arch_alias.c.arch == bindparam('arch'), 
                           recipe_table_alias.c.whiteboard == bindparam('recipe_whiteboard')),
                         
                     from_obj = [model.recipe_set_table.join(recipe_table_alias).
                                 join(model.task_result_table,model.task_result_table.c.id == recipe_table_alias.c.result_id).
                                 join(model.distro_table, model.distro_table.c.id == recipe_table_alias.c.distro_id).
                                 join(arch_alias, arch_alias.c.id == model.distro_table.c.arch_id).
                                 join(model.recipe_task_table, model.recipe_task_table.c.recipe_id == recipe_table_alias.c.id).
                                 join(model.task_table, model.task_table.c.id == model.recipe_task_table.c.task_id)]).alias('foo')
                   
        #If this query starts to bog down and slow up, we could create a view for the inner select (s2)
        #SQLAlchemy Select object does not really support this,I think you would have to use SQLAlchemy text for s2, and then
        #build a specific table for it
        #eng = database.get_engine()
        #c = s2.compile(eng) 
        #eng.execute("CREATE VIEW foobar AS %s" % c) 
      
        class OuterDynamo(object):
            pass

        result_data = []    
        my_hash = {}
       
        from_objs = []
        select_container = {}
        for arch_val,whiteboard_val in whiteboard_data.iteritems():
            s2 = s2.params(arch=arch_val)
            s2 = s2.params(recipe_whiteboard=whiteboard_val)
            #s1 = 's1_%s' % arch_val
            s1  = select([func.count(s2.c.result),
                                  func.sum(s2.c.rc0).label('New'),
                                  func.sum(s2.c.rc1).label('Pass'),
                                  func.sum(s2.c.rc2).label('Warn'),
                                  func.sum(s2.c.rc3).label('Fail'),
                                  func.sum(s2.c.rc4).label('Panic'),
                                  s2.c.arch,
                                  model.task_table.c.name.label('task_name'),  
                                  s2.c.task_id.label('task_id_pk')],
                                  s2.c.task_id == model.task_table.c.id,
                     
                                  from_obj=[model.task_table,s2]).group_by(model.task_table.c.name).order_by(model.task_table.c.name).alias()
          
            class InnerDynamo(object):
                pass
            mapper(InnerDynamo,s1)

            #from_objs.append(vars()['s1_%s' % arch_val])
            dyn = InnerDynamo.query()
            for d in dyn:
                result_data.append(d)
        return result_data
                #self.arches_used[d.arch] = 1 
                #if d.task_name not in my_hash:
                #    my_hash[d.task_name] = [d]
                #else:  
                #    my_hash[d.task_name].append(d)
                #log.debug('d is %s %s %s %s %s' % (d.arch,d.New, d.Pass, d.Fail, d.task_name) )                
           
            #dyn = InnerDynamo.query()
            #outer_from_fields = []
           
            #log.debug('my_data is %s' % result_data)
            #result_data.append(InnerDynamo.query())

       
        #for k,v in my_hash.items():
        #     my_tuple = (k,)# + (elem for elem in v) 
        #   
        #  #  select_fields = []
        #    #pk_arch = ''
        #   # for elem in v:
        #    #    table_pointer = vars()['s1_%s' % elem.arch]
        #        if len(select_fields) == 0:
        #            pk_arch = elem.arch
        #            select_fields.append(table_pointer.c.task_name.label('outer_task_name'))
        #         
        #        select_fields.append(table_pointer.c.New.label('New_%s' % elem.arch))
        #        my_tuple += (elem,)
            #s3 = select(select_fields,from_obj=[
        #    s3 = select(select_fields,from_obj=from_objs) 
        #    #log.debug('vars are %s' % s3)
        #    res = s3.execute()
        #    for r in res:
        #        log.debug('Result row is %s' % r)
        #    mapper(OuterDynamo,s3,primary_key=[s3.c.outer_task_name])
        #    result_data.append(outer_dynamo)
        
      
       
