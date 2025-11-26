import TechnicianEnrollmentWorkflow from '../workflows/technicianEnrollment.workflow';

async function main() {
  // Disable external effects for local testing
  process.env.EMAIL_DISABLED = '1';
  process.env.DASHBOARD_DISABLED = '0'; // Enable dashboard to test posting

  const workflow = new TechnicianEnrollmentWorkflow();

  // Unique techId per run to avoid duplicate conflicts
  const uniqueTechId = `TECH-${Date.now()}`;

  // Minimal fake enrollment (adjust fields as needed for tests)
  const enrollmentData = {
    techId: uniqueTechId,
    name: 'Jamie Sample',
    email: 'jamie.sample@example.com',
    phone: '555-101-2020',
    vehicle: {
      year: '2021',
      make: 'Ford',
      model: 'Escape',
      color: 'White',
      plate: 'XYZ789',
      vin: '1HGCM82633A004352'
    },
    insurance: {
      provider: 'SecureCo',
      policyNumber: 'SC-98765',
      expiresOn: '2026-06-30'
    },
    acknowledgements: {
      mileageRule: true,
      byovPolicy: true,
      signature: 'Jamie Sample'
    },
    photos: []
  };

  try {
    console.log('Submitting enrollment...');
    const submitted = await workflow.submitEnrollment(enrollmentData);
    console.log('Submitted:', { id: submitted.id, status: submitted.status });

    console.log('Approving enrollment...');
    const approved = await workflow.reviewEnrollment(submitted.id, true, 'Admin User');
    console.log('Approved:', { id: approved.id, status: approved.status, approvedBy: approved.approvedBy });

  } catch (e: any) {
    console.error('Error during workflow run:', e.message || e);
  }
}

main();
