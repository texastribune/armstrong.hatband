from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.http import HttpResponse
from django.http import HttpResponseBadRequest, HttpResponseNotFound
from django.core.exceptions import ObjectDoesNotExist

try:
    from django.conf.urls import patterns, url
except ImportError:
    from django.conf.urls.defaults import patterns, url

from armstrong.core.arm_layout.utils import render_model

from ..http import JsonResponse


EXCLUDED_MODELS_FROM_FACETS = getattr(settings,
    "ARMSTRONG_EXCLUDED_MODELS_FROM_FACETS", [
        # usage: ("app_label", "model_name"),
        ('taggit', 'taggeditem'),
        ("arm_wells", "well"),
        ("arm_wells", "node"),
    ])

EXCLUDED_APPS_FROM_FACETS = getattr(settings,
    "ARMSTRONG_EXCLUDED_APPS_FROM_FACETS", [
        "admin", "arm_access", "auth", "contenttypes", "djcelery",
        "registration", "reversion", "sessions", "sites", "south"
    ])


class ArmstrongBaseMixin(object):
    url_prefix = "armstrong"


class GenericKeyFacetsMixin(ArmstrongBaseMixin):
    url = "search/generickey/facets/"

    def get_urls(self):
        urlpatterns = patterns('',
            url(r"^%s/%s$" % (self.url_prefix, self.url),
                self.admin_view(self.generic_key_facets),
                name="generic_key_facets",
            )
        )
        return urlpatterns + super(GenericKeyFacetsMixin, self).get_urls()

    def generic_key_facets(self, request):
        """Find all available facets/Models for VisualSearch"""

        excluded_apps = Q(app_label__in=EXCLUDED_APPS_FROM_FACETS)
        excluded_models = Q()
        for app_label, model in EXCLUDED_MODELS_FROM_FACETS:
            excluded_models = excluded_models | Q(app_label=app_label,
                    model=model)
        values = "model", "app_label", "id"
        content_types = ContentType.objects.values_list(*values) \
                .exclude(excluded_apps | excluded_models)
        return JsonResponse(dict([(str(a), {"app_label": str(b), "id": str(c)})
                for a, b, c in content_types]))


class ModelSearchBackfillMixin(object):
    slug = "search"
    view_name_template = "%s_%s_search"

    def get_urls(self):
        # TODO: Attempt
        model_urls = []
        for model, model_admin in self._registry.iteritems():
            model_urls.append(
                    url(r"^%s/%s/%s/$" % (
                            model._meta.app_label,
                            model._meta.object_name.lower(),
                            self.slug),
                    self.admin_view(self.generic_key_modelsearch),
                    kwargs={'app_label': model._meta.app_label,
                            'model_name': model._meta.object_name.lower()},
                    name=self.view_name_template % (
                            model._meta.app_label,
                            model._meta.object_name.lower()))
                )

        return patterns('', *model_urls) \
                + super(ModelSearchBackfillMixin, self).get_urls()

    def generic_key_modelsearch(self, request, app_label, model_name):
        """
        Find instances for the requested model and return them as JSON.
        # TODO: add test coverage for this

        We don't have to worry about invalid app_label/model_name parameters
        because the URLs are pre-built with the kwargs in `get_urls()`.
        """
        content_type = ContentType.objects.get(app_label=app_label,
                model=model_name)

        model = content_type.model_class()
        model_admin = self._registry[model].__class__(model, self)
        model_admin.change_list_template = "admin/hatband/change_list.json"
        return model_admin.changelist_view(request)


class ModelPreviewMixin(ArmstrongBaseMixin):
    """
    Provides a way to render a model's preview display
    """
    slug = "render_model_preview"

    def get_urls(self):
        urlpatterns = patterns('',
            url(r"^%s/%s/$" % (self.url_prefix, self.slug),
                self.admin_view(self.render_model_preview),
                name="render_model_preview"
            )
        )
        return urlpatterns + super(ModelPreviewMixin, self).get_urls()

    def render_model_preview(self, request):
        try:
            content_type_id = int(request.GET["content_type"])
            object_id = int(request.GET["object_id"])
        except (ValueError, KeyError):
            return HttpResponseBadRequest()

        try:
            content_type = ContentType.objects.get(pk=content_type_id)
            model = content_type.model_class()
            result = model.objects.get(pk=object_id)
        except ObjectDoesNotExist:
            return HttpResponseNotFound()

        template = request.GET.get("template", "preview")
        return HttpResponse(render_model(result, template))


class TypeAndModelQueryMixin(ArmstrongBaseMixin):
    type_and_model_to_query_url = "search/type_and_model_to_query/"

    def get_urls(self):
        urlpatterns = patterns('',
            url(r"^%s/%s$" % (self.url_prefix,
                              self.type_and_model_to_query_url),
                self.admin_view(self.type_and_model_to_query),
                name="type_and_model_to_query",
            )
        )
        return urlpatterns + super(TypeAndModelQueryMixin, self).get_urls()

    def type_and_model_to_query(self, request):
        """
        Return JSON for an individual Model instance

        If the required parameters are wrong, return 400 Bad Request
        If the parameters are correct but there is no data, return empty JSON

        """
        try:
            content_type_id = request.GET["content_type_id"]
            object_id = request.GET["object_id"]
        except KeyError:
            return HttpResponseBadRequest()

        try:
            content_type = ContentType.objects.get(pk=content_type_id)
            model = content_type.model_class()
            result = model.objects.get(pk=object_id)
        except ObjectDoesNotExist:
            data = ""
        else:
            data = '%s: "%d: %s"' % (content_type.model, result.pk, result)

        return JsonResponse({"query": data})
