"""Account for every declared image region; never equate layout with a whole page."""
from editor.source_alignment import valid_box

VERSION = 'declared-picture-coverage-v1'


def selected_regions(layout, limit=3):
    regions = [r for r in layout.get('regions', [])
               if r.get('type') == 'PICTURE' and valid_box(r.get('bbox'))]
    # Preserve the established inference budget. Small regions remain explicitly
    # unobserved; an icon must not automatically trigger an expensive VLM call.
    large = [r for r in regions if r['bbox'][2]*r['bbox'][3] > .06]
    return large[:limit]


def coverage(layout, observations, limit=3):
    pictures = [r for r in layout.get('regions', []) if r.get('type') == 'PICTURE']
    selected = selected_regions(layout, limit)
    entries = []
    for index, region in enumerate(pictures):
        matches = [i for i, observation in enumerate(observations)
                   if observation.get('region_bbox') == region.get('bbox')]
        reason = ('INVALID_REGION_GEOMETRY' if not valid_box(region.get('bbox'))
                  else 'BELOW_MINIMUM_AREA' if region['bbox'][2]*region['bbox'][3] <= .06
                  else 'REGION_BUDGET_LIMIT' if region not in selected
                  else 'OBSERVATION_MISSING' if not matches else None)
        entries.append({'picture_index':index, 'source_ref':region.get('source_ref'),
                        'bbox':region.get('bbox'), 'observation_indices':matches,
                        'status':'UNOBSERVED' if reason else 'OBSERVED_CANDIDATE', 'reason':reason})
    missing = sum(row['status']=='UNOBSERVED' for row in entries)
    return {'method':VERSION, 'declared_picture_regions':len(pictures),
            'selected_picture_regions':len(selected), 'unobserved_picture_regions':missing,
            'regions':entries, 'declared_region_coverage':'INCOMPLETE' if missing else 'OBSERVED' if pictures else 'NO_DECLARED_PICTURES',
            'whole_page_visual_coverage':'NOT_VERIFIED',
            'figure_coverage':'NOT_VERIFIED', 'semantic_acceptance':False}
