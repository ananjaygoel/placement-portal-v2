/**
 * Placement Portal Application (PPA) - Vue.js Frontend
 * Main application component with all dashboard functionality
 * Supports Admin, Company, and Student roles
 */

const { createApp } = Vue;

createApp({
  data() {
    return {
      mode: 'login',
      adminSection: 'companies',
      companySection: 'jobs',
      studentSection: 'jobs',
      loading: false,
      message: '',
      error: '',
      token: localStorage.getItem('ppa_token') || '',
      currentUser: {},
      dashboard: null,
      companies: [],
      students: [],
      drives: [],
      applications: [],
      companyJobs: [],
      companyApplications: [],
      companyInterviews: [],
      companyExports: [],
      companyReports: [],
      companyNotifications: [],
      studentJobs: [],
      studentApplications: [],
      studentInterviews: [],
      studentExports: [],
      studentNotifications: [],
      companyFilters: {
        q: '',
        industry: '',
        approval_status: ''
      },
      studentFilters: {
        q: ''
      },
      driveFilters: {
        q: '',
        status: ''
      },
      applicationFilters: {
        q: '',
        status: ''
      },
      companyJobFilters: {
        q: '',
        status: ''
      },
      companyApplicationFilters: {
        q: '',
        status: '',
        job_id: ''
      },
      companyInterviewFilters: {
        status: '',
        job_id: ''
      },
      companyReportFilters: {
        month_label: '',
        format: ''
      },
      studentJobFilters: {
        q: '',
        company: '',
        skills: ''
      },
      studentApplicationFilters: {
        q: '',
        status: ''
      },
      studentInterviewFilters: {
        status: ''
      },
      companyJobForm: {
        title: '',
        description: '',
        skills_required: '',
        experience_required: '',
        salary: null,
        benefits: '',
        application_deadline: '',
        eligibility_branch: '',
        minimum_cgpa: null,
        minimum_graduation_year: null
      },
      studentProfileForm: {
        full_name: '',
        education: '',
        experience: '',
        skills: '',
        resume_url: '',
        branch: '',
        graduation_year: null,
        cgpa: null,
        contact_number: ''
      },
      loginForm: { email: '', password: '' },
      studentForm: {
        full_name: '',
        email: '',
        password: '',
        contact_number: '',
        branch: '',
        graduation_year: null,
        cgpa: null
      },
      companyForm: {
        company_name: '',
        email: '',
        password: '',
        industry: '',
        location: '',
        hr_contact: ''
      }
    };
  },
  async mounted() {
    if (this.token) {
      await this.bootstrapSession();
    }
  },
  methods: {
    resetAlerts() {
      this.message = '';
      this.error = '';
    },
    toQuery(params) {
      const query = new URLSearchParams();
      Object.entries(params).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== '') {
          query.append(key, value);
        }
      });
      const queryString = query.toString();
      return queryString ? `?${queryString}` : '';
    },
    async requestJson(url, options = {}) {
      const response = await fetch(url, options);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || data.message || 'Request failed');
      }
      return data;
    },
    authHeaders() {
      return {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.token}`
      };
    },
    async registerStudent() {
      this.resetAlerts();
      this.loading = true;
      try {
        const data = await this.requestJson('/api/auth/register/student', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.studentForm)
        });
        this.message = data.message;
        this.mode = 'login';
        this.studentForm = { full_name: '', email: '', password: '', contact_number: '', branch: '', graduation_year: null, cgpa: null };
      } catch (err) {
        this.error = err.message;
      } finally {
        this.loading = false;
      }
    },
    async registerCompany() {
      this.resetAlerts();
      this.loading = true;
      try {
        const data = await this.requestJson('/api/auth/register/company', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.companyForm)
        });
        this.message = data.message;
        this.mode = 'login';
        this.companyForm = { company_name: '', email: '', password: '', industry: '', location: '', hr_contact: '' };
      } catch (err) {
        this.error = err.message;
      } finally {
        this.loading = false;
      }
    },
    async login() {
      this.resetAlerts();
      this.loading = true;
      try {
        const data = await this.requestJson('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.loginForm)
        });
        this.token = data.access_token;
        localStorage.setItem('ppa_token', this.token);
        this.currentUser = data.user;
        window.location.hash = `${data.user.role}-dashboard`;
        await this.loadDashboard();
        this.message = `Login successful. Redirected to ${data.user.role} dashboard.`;
      } catch (err) {
        this.error = err.message;
      } finally {
        this.loading = false;
      }
    },
    async bootstrapSession() {
      try {
        const meData = await this.requestJson('/api/auth/me', { headers: this.authHeaders() });
        this.currentUser = meData;
        if (!window.location.hash) {
          window.location.hash = `${this.currentUser.role}-dashboard`;
        }
        await this.loadDashboard();
      } catch (err) {
        this.logout();
      }
    },
    async loadDashboard() {
      this.resetAlerts();
      if (!this.currentUser.role) return;
      try {
        const endpoint = this.currentUser.role === 'admin'
          ? '/api/admin/overview'
          : this.currentUser.role === 'company'
            ? '/api/company/overview'
            : '/api/student/overview';
        this.dashboard = await this.requestJson(endpoint, { headers: this.authHeaders() });
        if (this.currentUser.role === 'admin') {
          await this.loadAdminManagementData();
        }
        if (this.currentUser.role === 'company') {
          await this.loadCompanyManagementData();
        }
        if (this.currentUser.role === 'student') {
          this.syncStudentProfileForm();
          await this.loadStudentManagementData();
        }
      } catch (err) {
        this.error = err.message;
      }
    },
    async loadAdminManagementData() {
      await Promise.all([
        this.fetchCompanies(),
        this.fetchStudents(),
        this.fetchDrives(),
        this.fetchApplications()
      ]);
    },
    async loadCompanyManagementData() {
      await Promise.all([
        this.fetchCompanyJobs(),
        this.fetchCompanyApplications(),
        this.fetchCompanyInterviews(),
        this.fetchCompanyExports(),
        this.fetchCompanyReports(),
        this.fetchCompanyNotifications()
      ]);
    },
    syncStudentProfileForm() {
      if (!this.dashboard || !this.dashboard.student) return;
      this.studentProfileForm = {
        full_name: this.dashboard.student.full_name || '',
        education: this.dashboard.student.education || '',
        experience: this.dashboard.student.experience || '',
        skills: this.dashboard.student.skills || '',
        resume_url: this.dashboard.student.resume_url || '',
        branch: this.dashboard.student.branch || '',
        graduation_year: this.dashboard.student.graduation_year,
        cgpa: this.dashboard.student.cgpa,
        contact_number: this.dashboard.student.contact_number || ''
      };
    },
    async loadStudentManagementData() {
      await Promise.all([
        this.fetchStudentJobs(),
        this.fetchStudentApplications(),
        this.fetchStudentInterviews(),
        this.fetchStudentExports(),
        this.fetchStudentNotifications()
      ]);
    },
    async fetchCompanies() {
      try {
        const query = this.toQuery(this.companyFilters);
        const data = await this.requestJson(`/api/admin/companies${query}`, { headers: this.authHeaders() });
        this.companies = data.companies || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async setCompanyApproval(companyId, approvalStatus) {
      try {
        await this.requestJson(`/api/admin/companies/${companyId}/approval`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify({ approval_status: approvalStatus })
        });
        await this.loadDashboard();
        this.message = 'Company approval updated';
      } catch (err) {
        this.error = err.message;
      }
    },
    async toggleCompanyBlacklist(companyId, isBlacklisted) {
      try {
        await this.requestJson(`/api/admin/companies/${companyId}/status`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify({ is_blacklisted: isBlacklisted })
        });
        await this.loadDashboard();
        this.message = 'Company blacklist status updated';
      } catch (err) {
        this.error = err.message;
      }
    },
    async toggleCompanyActive(companyId, isActive) {
      try {
        await this.requestJson(`/api/admin/companies/${companyId}/status`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify({ is_active: isActive })
        });
        await this.loadDashboard();
        this.message = 'Company active status updated';
      } catch (err) {
        this.error = err.message;
      }
    },
    async removeCompany(companyId) {
      if (!window.confirm('Remove this company profile?')) return;
      try {
        await this.requestJson(`/api/admin/companies/${companyId}`, {
          method: 'DELETE',
          headers: this.authHeaders()
        });
        await this.loadDashboard();
        this.message = 'Company removed successfully';
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchStudents() {
      try {
        const query = this.toQuery(this.studentFilters);
        const data = await this.requestJson(`/api/admin/students${query}`, { headers: this.authHeaders() });
        this.students = data.students || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async toggleStudentBlacklist(studentId, isBlacklisted) {
      try {
        await this.requestJson(`/api/admin/students/${studentId}/status`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify({ is_blacklisted: isBlacklisted })
        });
        await this.loadDashboard();
        this.message = 'Student blacklist status updated';
      } catch (err) {
        this.error = err.message;
      }
    },
    async toggleStudentActive(studentId, isActive) {
      try {
        await this.requestJson(`/api/admin/students/${studentId}/status`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify({ is_active: isActive })
        });
        await this.loadDashboard();
        this.message = 'Student active status updated';
      } catch (err) {
        this.error = err.message;
      }
    },
    async removeStudent(studentId) {
      if (!window.confirm('Remove this student profile?')) return;
      try {
        await this.requestJson(`/api/admin/students/${studentId}`, {
          method: 'DELETE',
          headers: this.authHeaders()
        });
        await this.loadDashboard();
        this.message = 'Student removed successfully';
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchDrives() {
      try {
        const query = this.toQuery(this.driveFilters);
        const data = await this.requestJson(`/api/admin/drives${query}`, { headers: this.authHeaders() });
        this.drives = data.drives || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async updateDriveStatus(driveId, status) {
      try {
        await this.requestJson(`/api/admin/drives/${driveId}/status`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify({ status })
        });
        await this.loadDashboard();
        this.message = 'Drive status updated';
      } catch (err) {
        this.error = err.message;
      }
    },
    async removeDrive(driveId) {
      if (!window.confirm('Remove this job posting?')) return;
      try {
        await this.requestJson(`/api/admin/drives/${driveId}`, {
          method: 'DELETE',
          headers: this.authHeaders()
        });
        await this.loadDashboard();
        this.message = 'Drive removed successfully';
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchApplications() {
      try {
        const query = this.toQuery(this.applicationFilters);
        const data = await this.requestJson(`/api/admin/applications${query}`, { headers: this.authHeaders() });
        this.applications = data.applications || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async updateApplicationStatus(applicationId, status) {
      const payload = { status };
      if (['offer', 'placed'].includes(status)) {
        const offeredSalary = window.prompt('Enter offered salary (optional):', '');
        if (offeredSalary !== null && offeredSalary !== '') {
          payload.offered_salary = offeredSalary;
        }
      }
      if (status === 'placed') {
        const joiningDate = window.prompt('Enter joining date (YYYY-MM-DD):', '');
        if (!joiningDate) {
          this.error = 'joining_date is required for placed status';
          return;
        }
        payload.joining_date = joiningDate;
      }
      const feedback = window.prompt('Admin feedback/remarks (optional):', '');
      if (feedback) {
        payload.feedback = feedback;
        payload.remarks = feedback;
      }
      try {
        await this.requestJson(`/api/admin/applications/${applicationId}/status`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify(payload)
        });
        await this.loadDashboard();
        this.message = 'Application status updated';
      } catch (err) {
        this.error = err.message;
      }
    },
    async removeApplication(applicationId) {
      if (!window.confirm('Remove this application?')) return;
      try {
        await this.requestJson(`/api/admin/applications/${applicationId}`, {
          method: 'DELETE',
          headers: this.authHeaders()
        });
        await this.loadDashboard();
        this.message = 'Application removed successfully';
      } catch (err) {
        this.error = err.message;
      }
    },
    async createCompanyJob() {
      try {
        await this.requestJson('/api/company/jobs', {
          method: 'POST',
          headers: this.authHeaders(),
          body: JSON.stringify(this.companyJobForm)
        });
        this.message = 'Job posted successfully and sent for admin approval';
        this.companyJobForm = {
          title: '',
          description: '',
          skills_required: '',
          experience_required: '',
          salary: null,
          benefits: '',
          application_deadline: '',
          eligibility_branch: '',
          minimum_cgpa: null,
          minimum_graduation_year: null
        };
        await this.loadDashboard();
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchCompanyJobs() {
      try {
        const query = this.toQuery(this.companyJobFilters);
        const data = await this.requestJson(`/api/company/jobs${query}`, {
          headers: this.authHeaders()
        });
        this.companyJobs = data.jobs || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async updateCompanyJobStatus(jobId, status) {
      try {
        await this.requestJson(`/api/company/jobs/${jobId}/status`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify({ status })
        });
        this.message = 'Job status updated';
        await this.loadDashboard();
      } catch (err) {
        this.error = err.message;
      }
    },
    async openJobApplicants(job) {
      this.companySection = 'applications';
      this.companyApplicationFilters.job_id = String(job.id);
      await this.fetchCompanyApplications();
    },
    async fetchCompanyApplications() {
      try {
        const query = this.toQuery(this.companyApplicationFilters);
        const data = await this.requestJson(`/api/company/applications${query}`, {
          headers: this.authHeaders()
        });
        this.companyApplications = data.applications || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async viewCompanyStudentProfile(studentId) {
      try {
        const data = await this.requestJson(`/api/company/students/${studentId}`, {
          headers: this.authHeaders()
        });
        const profile = data.student;
        const latest = data.applications[0];
        window.alert(
          `Student: ${profile.full_name}\n` +
          `Email: ${profile.email || 'N/A'}\n` +
          `Contact: ${profile.contact_number || 'N/A'}\n` +
          `Education: ${profile.education || 'N/A'}\n` +
          `Skills: ${profile.skills || 'N/A'}\n` +
          `Latest Application: ${latest ? latest.job_title + ' (' + latest.status + ')' : 'N/A'}`
        );
      } catch (err) {
        this.error = err.message;
      }
    },
    async updateCompanyApplicationStatus(applicationId, status) {
      const feedback = window.prompt('Enter feedback for applicant (optional):', '') || '';
      const payload = { status, feedback };
      if (['offer', 'placed'].includes(status)) {
        const offeredSalary = window.prompt('Enter offered salary (optional):', '');
        if (offeredSalary !== null && offeredSalary !== '') {
          payload.offered_salary = offeredSalary;
        }
      }
      if (status === 'placed') {
        const joiningDate = window.prompt('Enter joining date (YYYY-MM-DD):', '');
        if (!joiningDate) {
          this.error = 'joining_date is required for placed status';
          return;
        }
        payload.joining_date = joiningDate;
      }
      try {
        await this.requestJson(`/api/company/applications/${applicationId}/status`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify(payload)
        });
        this.message = 'Application status shared with applicant';
        await this.loadDashboard();
      } catch (err) {
        this.error = err.message;
      }
    },
    async scheduleInterviewForApplication(application) {
      const scheduledAt = window.prompt('Enter interview datetime (YYYY-MM-DDTHH:MM):', '');
      if (!scheduledAt) return;
      const interviewMode = (window.prompt('Interview mode (virtual / in_person / phone):', 'virtual') || 'virtual').trim();
      const meetingLink = window.prompt('Meeting link (optional):', '') || '';
      const location = window.prompt('Interview location (optional):', '') || '';
      const notes = window.prompt('Interview notes (optional):', '') || '';

      try {
        await this.requestJson(`/api/company/applications/${application.id}/interviews`, {
          method: 'POST',
          headers: this.authHeaders(),
          body: JSON.stringify({
            scheduled_at: scheduledAt,
            interview_mode: interviewMode,
            meeting_link: meetingLink,
            location,
            notes
          })
        });
        this.message = 'Interview scheduled successfully';
        this.companySection = 'interviews';
        await this.loadDashboard();
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchCompanyInterviews() {
      try {
        const query = this.toQuery(this.companyInterviewFilters);
        const data = await this.requestJson(`/api/company/interviews${query}`, {
          headers: this.authHeaders()
        });
        this.companyInterviews = data.interviews || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async updateCompanyInterviewStatus(interviewId, status) {
      const notes = window.prompt('Update interview notes (optional):', '') || '';
      try {
        await this.requestJson(`/api/company/interviews/${interviewId}/status`, {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify({ status, notes })
        });
        this.message = 'Interview status updated';
        await this.loadDashboard();
      } catch (err) {
        this.error = err.message;
      }
    },
    async requestCompanyExport() {
      try {
        const data = await this.requestJson('/api/company/exports', {
          method: 'POST',
          headers: this.authHeaders(),
          body: JSON.stringify({ scope: 'company_history' })
        });
        this.message = data.message || 'Export job queued successfully';
        this.companySection = 'exports';
        await this.fetchCompanyExports();
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchCompanyExports() {
      try {
        const data = await this.requestJson('/api/company/exports', {
          headers: this.authHeaders()
        });
        this.companyExports = data.exports || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async downloadCompanyExport(exportJobId) {
      try {
        const response = await fetch(`/api/company/exports/${exportJobId}/download`, {
          headers: this.authHeaders()
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || 'Unable to download export');
        }
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = downloadUrl;
        anchor.download = `company_export_${exportJobId}.csv`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.URL.revokeObjectURL(downloadUrl);
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchCompanyReports() {
      try {
        const query = this.toQuery(this.companyReportFilters);
        const data = await this.requestJson(`/api/company/reports${query}`, {
          headers: this.authHeaders()
        });
        this.companyReports = data.reports || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async downloadCompanyReport(reportId) {
      try {
        const response = await fetch(`/api/company/reports/${reportId}/download`, {
          headers: this.authHeaders()
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || 'Unable to download report');
        }
        const blob = await response.blob();
        const contentDisposition = response.headers.get('Content-Disposition') || '';
        const fileNameMatch = contentDisposition.match(/filename=\"?([^"]+)\"?/i);
        const fileName = fileNameMatch && fileNameMatch[1] ? fileNameMatch[1] : `placement_report_${reportId}`;
        const downloadUrl = window.URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = downloadUrl;
        anchor.download = fileName;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.URL.revokeObjectURL(downloadUrl);
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchCompanyNotifications() {
      try {
        const data = await this.requestJson('/api/company/notifications', {
          headers: this.authHeaders()
        });
        this.companyNotifications = data.notifications || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async markCompanyNotificationRead(notificationId) {
      try {
        await this.requestJson(`/api/company/notifications/${notificationId}/read`, {
          method: 'PATCH',
          headers: this.authHeaders()
        });
        await this.fetchCompanyNotifications();
        await this.loadDashboard();
      } catch (err) {
        this.error = err.message;
      }
    },
    async updateStudentProfile() {
      try {
        await this.requestJson('/api/student/profile', {
          method: 'PATCH',
          headers: this.authHeaders(),
          body: JSON.stringify(this.studentProfileForm)
        });
        this.message = 'Student profile updated';
        await this.loadDashboard();
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchStudentJobs() {
      try {
        const query = this.toQuery(this.studentJobFilters);
        const data = await this.requestJson(`/api/student/jobs${query}`, {
          headers: this.authHeaders()
        });
        this.studentJobs = data.jobs || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async applyToStudentJob(jobId) {
      try {
        await this.requestJson(`/api/student/jobs/${jobId}/apply`, {
          method: 'POST',
          headers: this.authHeaders()
        });
        this.message = 'Application submitted successfully';
        this.studentSection = 'applications';
        await this.loadDashboard();
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchStudentApplications() {
      try {
        const query = this.toQuery(this.studentApplicationFilters);
        const data = await this.requestJson(`/api/student/applications${query}`, {
          headers: this.authHeaders()
        });
        this.studentApplications = data.applications || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchStudentInterviews() {
      try {
        const query = this.toQuery(this.studentInterviewFilters);
        const data = await this.requestJson(`/api/student/interviews${query}`, {
          headers: this.authHeaders()
        });
        this.studentInterviews = data.interviews || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async requestStudentExport() {
      try {
        const data = await this.requestJson('/api/student/exports', {
          method: 'POST',
          headers: this.authHeaders(),
          body: JSON.stringify({ scope: 'student_history' })
        });
        this.message = data.message || 'Export job queued successfully';
        this.studentSection = 'exports';
        await this.fetchStudentExports();
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchStudentExports() {
      try {
        const data = await this.requestJson('/api/student/exports', {
          headers: this.authHeaders()
        });
        this.studentExports = data.exports || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async downloadStudentExport(exportJobId) {
      try {
        const response = await fetch(`/api/student/exports/${exportJobId}/download`, {
          headers: this.authHeaders()
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || 'Unable to download export');
        }
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = downloadUrl;
        anchor.download = `student_export_${exportJobId}.csv`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.URL.revokeObjectURL(downloadUrl);
      } catch (err) {
        this.error = err.message;
      }
    },
    async fetchStudentNotifications() {
      try {
        const data = await this.requestJson('/api/student/notifications', {
          headers: this.authHeaders()
        });
        this.studentNotifications = data.notifications || [];
      } catch (err) {
        this.error = err.message;
      }
    },
    async markStudentNotificationRead(notificationId) {
      try {
        await this.requestJson(`/api/student/notifications/${notificationId}/read`, {
          method: 'PATCH',
          headers: this.authHeaders()
        });
        await this.fetchStudentNotifications();
        await this.loadDashboard();
      } catch (err) {
        this.error = err.message;
      }
    },
    async downloadStudentDocument(applicationId, documentType) {
      try {
        const response = await fetch(`/api/student/applications/${applicationId}/${documentType}`, {
          headers: this.authHeaders()
        });
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || 'Unable to download document');
        }
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = downloadUrl;
        anchor.download = documentType === 'offer-letter'
          ? `offer_letter_application_${applicationId}.txt`
          : `placement_confirmation_application_${applicationId}.txt`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.URL.revokeObjectURL(downloadUrl);
      } catch (err) {
        this.error = err.message;
      }
    },
    logout() {
      localStorage.removeItem('ppa_token');
      this.token = '';
      this.currentUser = {};
      this.dashboard = null;
      this.companies = [];
      this.students = [];
      this.drives = [];
      this.applications = [];
      this.companyJobs = [];
      this.companyApplications = [];
      this.companyInterviews = [];
      this.companyExports = [];
      this.companyReports = [];
      this.companyNotifications = [];
      this.studentJobs = [];
      this.studentApplications = [];
      this.studentInterviews = [];
      this.studentExports = [];
      this.studentNotifications = [];
      window.location.hash = '';
      this.message = 'Logged out successfully.';
    }
  }
}).mount('#app');
