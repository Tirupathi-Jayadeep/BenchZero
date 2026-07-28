from datetime import date, timedelta
from django.core.management.base import BaseCommand
from staffing.models import (
    Skill, Developer, DeveloperSkill, Project, ProjectSlot, 
    SlotSkillRequirement, Allocation, SolverRun, AllocationProposal
)
from staffing.solver.runner import run_optimization_engine

class Command(BaseCommand):
    help = "Seed database with realistic developers, skills, projects, slots, and run initial optimization solver"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Seeding BenchZero database..."))

        # Clear existing data
        AllocationProposal.objects.all().delete()
        SolverRun.objects.all().delete()
        Allocation.objects.all().delete()
        SlotSkillRequirement.objects.all().delete()
        ProjectSlot.objects.all().delete()
        Project.objects.all().delete()
        DeveloperSkill.objects.all().delete()
        Developer.objects.all().delete()
        Skill.objects.all().delete()

        # 1. Create Skills
        skills_data = [
            ("Python", "backend", "Backend development with Python & Django/FastAPI"),
            ("Django", "backend", "Web framework for perfectionists with deadlines"),
            ("Node.js", "backend", "Asynchronous event-driven JavaScript runtime"),
            ("Go", "backend", "Statically typed concurrent backend language"),
            ("Java", "backend", "Enterprise application platform"),
            ("React", "frontend", "Declarative component-based UI framework"),
            ("TypeScript", "frontend", "Typed JavaScript at scale"),
            ("Vue.js", "frontend", "Progressive frontend framework"),
            ("PostgreSQL", "database", "Advanced open-source relational database"),
            ("Redis", "database", "In-memory cache and message broker"),
            ("AWS", "devops", "Amazon Web Services cloud platform"),
            ("Docker", "devops", "Containerization engine"),
            ("Kubernetes", "devops", "Container orchestration system"),
            ("PyTorch", "ai_ml", "Deep learning & machine learning framework"),
            ("MLOps", "ai_ml", "Machine learning model deployment & monitoring"),
            ("Data Engineering", "ai_ml", "ETL pipelines and big data processing"),
        ]

        skills_dict = {}
        for name, cat, desc in skills_data:
            s = Skill.objects.create(name=name, category=cat, description=desc)
            skills_dict[name] = s

        # 2. Create Developers
        devs_raw = [
            ("Alice Chen", "alice@benchzero.io", "Staff AI Architect", 150.00, [("Python", 5), ("PyTorch", 5), ("MLOps", 4), ("PostgreSQL", 4), ("Docker", 4)]),
            ("Bob Smith", "bob@benchzero.io", "Principal Fullstack Lead", 140.00, [("React", 5), ("TypeScript", 5), ("Node.js", 4), ("Python", 4), ("PostgreSQL", 4)]),
            ("Charlie Davis", "charlie@benchzero.io", "Senior Backend Engineer", 110.00, [("Python", 5), ("Django", 5), ("PostgreSQL", 5), ("Redis", 4), ("Docker", 4)]),
            ("Diana Prince", "diana@benchzero.io", "Senior DevOps Specialist", 125.00, [("AWS", 5), ("Docker", 5), ("Kubernetes", 5), ("Python", 3), ("Go", 4)]),
            ("Evan Wright", "evan@benchzero.io", "Frontend Architect", 130.00, [("React", 5), ("TypeScript", 5), ("Vue.js", 4), ("Node.js", 3)]),
            ("Fiona Gallagher", "fiona@benchzero.io", "Backend & Go Engineer", 105.00, [("Go", 5), ("PostgreSQL", 4), ("Docker", 4), ("Kubernetes", 3)]),
            ("George Clark", "george@benchzero.io", "Data & ML Engineer", 115.00, [("Python", 4), ("PyTorch", 4), ("Data Engineering", 5), ("PostgreSQL", 4)]),
            ("Hannah Abbott", "hannah@benchzero.io", "Fullstack Developer", 95.00, [("React", 4), ("TypeScript", 4), ("Node.js", 4), ("PostgreSQL", 3)]),
            ("Ian Malcolm", "ian@benchzero.io", "Junior Python Developer", 70.00, [("Python", 3), ("Django", 3), ("PostgreSQL", 2)]),
            ("Julia Roberts", "julia@benchzero.io", "Senior Cloud Engineer", 120.00, [("AWS", 5), ("Kubernetes", 4), ("Docker", 5), ("Python", 4)]),
            ("Kevin Bacon", "kevin@benchzero.io", "Backend Specialist", 100.00, [("Java", 5), ("PostgreSQL", 4), ("Docker", 3)]),
            ("Laura Palmer", "laura@benchzero.io", "Frontend Specialist", 90.00, [("Vue.js", 5), ("TypeScript", 4), ("React", 3)]),
            ("Michael Scott", "michael@benchzero.io", "Lead Enterprise Architect", 160.00, [("Java", 5), ("AWS", 4), ("PostgreSQL", 5), ("Docker", 4)]),
            ("Nina Myers", "nina@benchzero.io", "AI Research Engineer", 135.00, [("PyTorch", 5), ("Python", 5), ("MLOps", 4), ("Data Engineering", 4)]),
            ("Oscar Martinez", "oscar@benchzero.io", "Database & Performance Lead", 125.00, [("PostgreSQL", 5), ("Redis", 5), ("Python", 4), ("Docker", 3)]),
        ]

        devs_dict = {}
        for name, email, title, cost, skill_list in devs_raw:
            d = Developer.objects.create(
                name=name,
                email=email,
                title=title,
                hourly_cost=cost,
                max_weekly_hours=40
            )
            devs_dict[name] = d
            for skill_name, level in skill_list:
                DeveloperSkill.objects.create(
                    developer=d,
                    skill=skills_dict[skill_name],
                    proficiency_level=level
                )

        # 3. Create Projects & Slots
        today = date.today()
        p1 = Project.objects.create(
            name="Apex Horizon AI Platform",
            client="Apex Financial",
            priority=5,
            budget=250000.00,
            description="Enterprise generative AI model integration and predictive analytics pipeline."
        )
        s1 = ProjectSlot.objects.create(
            project=p1,
            role_title="Lead AI & PyTorch Architect",
            start_date=today,
            end_date=today + timedelta(days=90),
            priority=5,
            headcount_needed=1,
            weekly_hours_required=40
        )
        SlotSkillRequirement.objects.create(project_slot=s1, skill=skills_dict["PyTorch"], min_proficiency=4, is_mandatory=True)
        SlotSkillRequirement.objects.create(project_slot=s1, skill=skills_dict["Python"], min_proficiency=4, is_mandatory=True)

        s2 = ProjectSlot.objects.create(
            project=p1,
            role_title="Senior Data Pipeline Engineer",
            start_date=today + timedelta(days=15),
            end_date=today + timedelta(days=105),
            priority=4,
            headcount_needed=1,
            weekly_hours_required=40
        )
        SlotSkillRequirement.objects.create(project_slot=s2, skill=skills_dict["Data Engineering"], min_proficiency=4, is_mandatory=True)
        SlotSkillRequirement.objects.create(project_slot=s2, skill=skills_dict["PostgreSQL"], min_proficiency=3, is_mandatory=True)

        p2 = Project.objects.create(
            name="Nexus Cloud Modernization",
            client="Nexus Global",
            priority=4,
            budget=180000.00,
            description="Migration of legacy services to Kubernetes infrastructure on AWS."
        )
        s3 = ProjectSlot.objects.create(
            project=p2,
            role_title="Lead Kubernetes Architect",
            start_date=today,
            end_date=today + timedelta(days=60),
            priority=5,
            headcount_needed=1,
            weekly_hours_required=40
        )
        SlotSkillRequirement.objects.create(project_slot=s3, skill=skills_dict["Kubernetes"], min_proficiency=4, is_mandatory=True)
        SlotSkillRequirement.objects.create(project_slot=s3, skill=skills_dict["AWS"], min_proficiency=4, is_mandatory=True)

        s4 = ProjectSlot.objects.create(
            project=p2,
            role_title="Go Microservices Developer",
            start_date=today + timedelta(days=10),
            end_date=today + timedelta(days=70),
            priority=3,
            headcount_needed=2,
            weekly_hours_required=40
        )
        SlotSkillRequirement.objects.create(project_slot=s4, skill=skills_dict["Go"], min_proficiency=3, is_mandatory=True)

        p3 = Project.objects.create(
            name="Velocity Next-Gen Dashboard",
            client="Velocity Mobility",
            priority=3,
            budget=120000.00,
            description="Real-time telematics dashboard built with React and TypeScript."
        )
        s5 = ProjectSlot.objects.create(
            project=p3,
            role_title="Principal React Frontend Engineer",
            start_date=today + timedelta(days=5),
            end_date=today + timedelta(days=65),
            priority=4,
            headcount_needed=1,
            weekly_hours_required=40
        )
        SlotSkillRequirement.objects.create(project_slot=s5, skill=skills_dict["React"], min_proficiency=4, is_mandatory=True)
        SlotSkillRequirement.objects.create(project_slot=s5, skill=skills_dict["TypeScript"], min_proficiency=4, is_mandatory=True)

        p4 = Project.objects.create(
            name="Quantum Core API Engine",
            client="Quantum Logistics",
            priority=5,
            budget=200000.00,
            description="High-throughput Django & Redis optimization for dispatch routing."
        )
        s6 = ProjectSlot.objects.create(
            project=p4,
            role_title="Lead Django & Redis Architect",
            start_date=today,
            end_date=today + timedelta(days=120),
            priority=5,
            headcount_needed=1,
            weekly_hours_required=40
        )
        SlotSkillRequirement.objects.create(project_slot=s6, skill=skills_dict["Django"], min_proficiency=4, is_mandatory=True)
        SlotSkillRequirement.objects.create(project_slot=s6, skill=skills_dict["Redis"], min_proficiency=4, is_mandatory=True)

        # 4. Trigger initial solver run to generate initial proposals and comparison metrics
        self.stdout.write("Executing initial CP-SAT solver optimization run...")
        run_result = run_optimization_engine(objective='balanced', time_limit_seconds=10.0, run_comparison=True)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully seeded BenchZero! Generated {len(devs_raw)} developers, {len(skills_data)} skills, "
            f"4 projects, {ProjectSlot.objects.count()} project slots, and SolverRun #{run_result['solver_run_id']} "
            f"with {run_result['proposals_count']} proposals."
        ))
