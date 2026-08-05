import json
import pytest
from datetime import date, timedelta
from io import BytesIO
from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APIClient
from staffing.models import Developer, Skill, Project, ProjectSlot, DeveloperSkill

from staffing.views import MAX_UPLOAD_ROWS

@pytest.mark.django_db
class TestFileUploads:

    def setup_method(self):
        self.client = APIClient()
        Developer.objects.filter(email__in=["jane@example.com", "john@example.com", "alice.s@example.com", "bob.m@example.com"]).delete()
        Project.objects.filter(name__in=["Titan Platform", "Helios App"]).delete()

    def test_developer_json_upload(self):
        json_data = [
            {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "title": "Lead Engineer",
                "hourly_cost": 120.0,
                "max_weekly_hours": 40,
                "skills": [
                    {"name": "Python", "proficiency_level": 5},
                    {"name": "React", "proficiency_level": 4}
                ]
            },
            {
                "name": "John Smith",
                "email": "john@example.com",
                "title": "Backend Dev",
                "hourly_cost": 95.0,
                "skills": [
                    {"name": "Python", "proficiency_level": 3}
                ]
            }
        ]

        json_bytes = json.dumps(json_data).encode('utf-8')
        from io import BytesIO
        file_obj = BytesIO(json_bytes)
        file_obj.name = "developers.json"

        response = self.client.post('/api/developers/upload/', {'file': file_obj}, format='multipart')
        assert response.status_code == 200, response.data
        data = response.json()
        assert (data['imported_count'] + data['updated_count']) == 2
        assert len(data['errors']) == 0

        dev_jane = Developer.objects.get(email="jane@example.com")
        assert dev_jane.name == "Jane Doe"
        assert dev_jane.developer_skills.count() == 2

    def test_developer_csv_upload(self):
        csv_content = (
            "name,email,title,hourly_cost,max_weekly_hours,skills\n"
            "Alice Springs,alice.s@example.com,DevOps Lead,130,40,AWS:5|Docker:4|Kubernetes:4\n"
            "Bob Marley,bob.m@example.com,Frontend Dev,90,40,React:4|TypeScript:4\n"
        )
        from io import BytesIO
        file_obj = BytesIO(csv_content.encode('utf-8'))
        file_obj.name = "developers.csv"

        response = self.client.post('/api/developers/upload/', {'file': file_obj}, format='multipart')
        assert response.status_code == 200, response.data
        data = response.json()
        assert (data['imported_count'] + data['updated_count']) == 2
        assert len(data['errors']) == 0

        dev_alice = Developer.objects.get(email="alice.s@example.com")
        assert dev_alice.name == "Alice Springs"
        assert dev_alice.developer_skills.count() == 3

    def test_developer_upload_validation_errors(self):
        csv_content = (
            "name,email,title,hourly_cost,max_weekly_hours,skills\n"
            ",invalidemail,Dev,100,40,Python:5\n"
        )
        from io import BytesIO
        file_obj = BytesIO(csv_content.encode('utf-8'))
        file_obj.name = "bad_devs.csv"

        response = self.client.post('/api/developers/upload/', {'file': file_obj}, format='multipart')
        assert response.status_code == 200
        data = response.json()
        assert data['imported_count'] == 0
        assert len(data['errors']) > 0

    def test_project_json_upload(self):
        today = date.today().isoformat()
        next_month = (date.today() + timedelta(days=30)).isoformat()
        
        json_data = [
            {
                "name": "Titan Platform",
                "client": "Titan Tech",
                "priority": 5,
                "budget": 200000.0,
                "description": "Next gen cloud platform",
                "slots": [
                    {
                        "role_title": "Cloud Architect",
                        "start_date": today,
                        "end_date": next_month,
                        "priority": 5,
                        "headcount_needed": 2,
                        "weekly_hours_required": 40,
                        "required_skills": [
                            {"name": "AWS", "min_proficiency": 4, "is_mandatory": True}
                        ]
                    }
                ]
            }
        ]

        from io import BytesIO
        file_obj = BytesIO(json.dumps(json_data).encode('utf-8'))
        file_obj.name = "projects.json"

        response = self.client.post('/api/projects/upload/', {'file': file_obj}, format='multipart')
        assert response.status_code == 200, response.data
        data = response.json()
        assert data['imported_projects_count'] == 1
        assert data['imported_slots_count'] == 1
        assert len(data['errors']) == 0

        project = Project.objects.get(name="Titan Platform")
        assert project.client == "Titan Tech"
        assert project.slots.count() == 1

    def test_project_csv_upload(self):
        today = date.today().isoformat()
        end = (date.today() + timedelta(days=60)).isoformat()
        csv_content = (
            "project_name,client,priority,budget,description,role_title,start_date,end_date,slot_priority,headcount_needed,weekly_hours_required,required_skills\n"
            f"Helios App,Helios Inc,4,80000,Mobile app,Senior iOS Engineer,{today},{end},4,1,40,Swift:4:mandatory|GraphQL:3:optional\n"
        )
        from io import BytesIO
        file_obj = BytesIO(csv_content.encode('utf-8'))
        file_obj.name = "projects.csv"

        response = self.client.post('/api/projects/upload/', {'file': file_obj}, format='multipart')
        assert response.status_code == 200, response.data
        data = response.json()
        assert data['imported_projects_count'] == 1
        assert data['imported_slots_count'] == 1

        proj = Project.objects.get(name="Helios App")
        slot = proj.slots.first()
        assert slot.role_title == "Senior iOS Engineer"
        assert slot.skill_requirements.count() == 2

    def test_invalid_email_with_valid_name_does_not_crash(self):
        """Regression test: a row with a VALID name but an INVALID email used
        to raise a bare NameError (DjangoValidationError was never imported)
        and 500 the whole request instead of being reported as a row error."""
        csv_content = (
            "name,email,title,hourly_cost,max_weekly_hours,skills\n"
            "Valid Name,not-an-email,Dev,100,40,Python:5\n"
        )
        file_obj = BytesIO(csv_content.encode('utf-8'))
        file_obj.name = "bad_email.csv"

        response = self.client.post('/api/developers/upload/', {'file': file_obj}, format='multipart')
        assert response.status_code == 200, response.content
        data = response.json()
        assert data['imported_count'] == 0
        assert any("Invalid email format" in e for e in data['errors'])

    def test_partial_batch_failure_does_not_roll_back_valid_rows(self):
        """One malformed row must not discard other rows that succeeded in
        the same request -- proves the per-row savepoint fix, not just the
        outer 'atomic' claim."""
        json_data = [
            {"name": "Good Dev", "email": "goodrow@example.com", "hourly_cost": 100, "max_weekly_hours": 40},
            {"name": "Bad Dev", "email": "not-an-email", "hourly_cost": 100, "max_weekly_hours": 40},
        ]
        try:
            file_obj = BytesIO(json.dumps(json_data).encode('utf-8'))
            file_obj.name = "mixed.json"
            response = self.client.post('/api/developers/upload/', {'file': file_obj}, format='multipart')
            assert response.status_code == 200, response.content
            data = response.json()
            assert data['imported_count'] == 1
            assert len(data['errors']) == 1
            assert Developer.objects.filter(email="goodrow@example.com").exists()
        finally:
            Developer.objects.filter(email="goodrow@example.com").delete()

    def test_existing_skills_not_mentioned_are_preserved(self):
        """Re-uploading a developer with a partial skills list must not wipe
        skills that were previously recorded but aren't mentioned this time."""
        try:
            dev = Developer.objects.create(name="Skill Keeper", email="keeper@example.com",
                                            hourly_cost=100, max_weekly_hours=40)
            python_skill, _ = Skill.objects.get_or_create(name="Python", defaults={'category': 'backend'})
            DeveloperSkill.objects.create(developer=dev, skill=python_skill, proficiency_level=4)

            json_data = [{
                "name": "Skill Keeper", "email": "keeper@example.com",
                "hourly_cost": 100, "max_weekly_hours": 40,
                "skills": [{"name": "Django", "proficiency_level": 3}],
            }]
            file_obj = BytesIO(json.dumps(json_data).encode('utf-8'))
            file_obj.name = "reupload.json"
            response = self.client.post('/api/developers/upload/', {'file': file_obj}, format='multipart')
            assert response.status_code == 200, response.content

            dev.refresh_from_db()
            skill_names = set(dev.developer_skills.values_list('skill__name', flat=True))
            assert skill_names == {"Python", "Django"}, "Existing skill was wiped by a partial re-upload"
        finally:
            Developer.objects.filter(email="keeper@example.com").delete()

    def test_reupload_updates_existing_project(self):
        """A second upload of the same (name, client) project should update
        its priority/budget/description, consistent with how Developer
        updates on a matching email -- not silently leave it stale."""
        try:
            json_data = [{"name": "Reupload Co", "client": "Acme", "priority": 2, "budget": 10000}]
            file_obj = BytesIO(json.dumps(json_data).encode('utf-8'))
            file_obj.name = "p1.json"
            self.client.post('/api/projects/upload/', {'file': file_obj}, format='multipart')

            json_data2 = [{"name": "Reupload Co", "client": "Acme", "priority": 5, "budget": 99000}]
            file_obj2 = BytesIO(json.dumps(json_data2).encode('utf-8'))
            file_obj2.name = "p2.json"
            response = self.client.post('/api/projects/upload/', {'file': file_obj2}, format='multipart')
            data = response.json()
            assert data['imported_projects_count'] == 0
            assert data['updated_projects_count'] == 1

            proj = Project.objects.get(name="Reupload Co", client="Acme")
            assert proj.priority == 5
            assert float(proj.budget) == 99000
        finally:
            Project.objects.filter(name="Reupload Co", client="Acme").delete()

    def test_file_too_large_is_rejected(self):
        oversized = BytesIO(b"x" * (5 * 1024 * 1024 + 1))
        oversized.name = "huge.csv"
        response = self.client.post('/api/developers/upload/', {'file': oversized}, format='multipart')
        assert response.status_code == 400
        assert "too large" in response.json()['error'].lower()

    def test_too_many_rows_is_rejected(self):
        json_data = [{"name": f"Dev {i}", "email": f"dev{i}@example.com"} for i in range(MAX_UPLOAD_ROWS + 1)]
        file_obj = BytesIO(json.dumps(json_data).encode('utf-8'))
        file_obj.name = "toolarge.json"
        response = self.client.post('/api/developers/upload/', {'file': file_obj}, format='multipart')
        assert response.status_code == 400
        assert "too many rows" in response.json()['error'].lower()

    @override_settings(REQUIRE_AUTH_FOR_WRITES=True)
    def test_upload_requires_staff_when_auth_required(self):
        """Bulk upload can touch the whole workforce in one call, so once
        auth is enforced it should require staff -- not just any logged-in
        user, unlike an ordinary single-record write."""
        User.objects.filter(username__in=['regular', 'staffer']).delete()
        regular_user = User.objects.create_user('regular', password='pw')
        self.client.force_authenticate(user=regular_user)

        json_data = [{"name": "Should Not Import", "email": "blocked@example.com"}]
        file_obj = BytesIO(json.dumps(json_data).encode('utf-8'))
        file_obj.name = "blocked.json"
        response = self.client.post('/api/developers/upload/', {'file': file_obj}, format='multipart')
        assert response.status_code == 403
        assert not Developer.objects.filter(email="blocked@example.com").exists()

        staff_user = User.objects.create_user('staffer', password='pw', is_staff=True)
        self.client.force_authenticate(user=staff_user)
        file_obj2 = BytesIO(json.dumps(json_data).encode('utf-8'))
        file_obj2.name = "allowed.json"
        response2 = self.client.post('/api/developers/upload/', {'file': file_obj2}, format='multipart')
        assert response2.status_code == 200
        Developer.objects.filter(email="blocked@example.com").delete()
        User.objects.filter(username__in=['regular', 'staffer']).delete()
