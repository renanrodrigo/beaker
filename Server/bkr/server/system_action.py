from turbogears import expose, validate
from cherrypy import HTTPError
from bkr.server import mail, identity
from bkr.server.model import System, Recipe, SystemActivity
from bkr.server.validators import CheckSystemValid, CheckRecipeValid

class SystemAction(object):

    @expose(format='json')
    @identity.require(identity.not_anonymous())
    @validate(validators = {'system' : CheckSystemValid(),
        'recipe_id' : CheckRecipeValid(),})
    def report_system_problem(self, system, description, recipe_id=None, tg_errors=None, **kw):
        if tg_errors:
            raise HTTPError(status=400, message=tg_errors)
        # CheckRecipeValid has converted the id into an ORM object
        if recipe_id is not None:
            recipe = recipe_id
        else:
            recipe = None
        mail.system_problem_report(system, description,
            recipe, identity.current.user)
        activity = SystemActivity(identity.current.user, u'WEBUI', u'Reported problem',
                u'Status', None, description)
        system.activity.append(activity)
        return {}
