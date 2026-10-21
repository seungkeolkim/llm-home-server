const path = require('node:path');
// CLI는 운영 서버가 관리하는 collection과 index를 새로 초기화하지 않습니다.
process.env.MONGO_AUTO_INDEX = 'false';
process.env.MONGO_AUTO_CREATE = 'false';
const mongoose = require('mongoose');
require('module-alias')({ base: path.resolve('/app/api') });
const { User } = require('@librechat/data-schemas').createModels(mongoose);
const connectDatabase = require('/app/config/connect');
const { registerUser } = require('~/server/services/AuthService');

/** stdin에서 받은 자격 증명으로 최초 local administrator만 생성합니다. */
async function provisionAdministrator() {
  let credentialInput = '';
  for await (const inputChunk of process.stdin) {
    credentialInput += inputChunk.toString();
  }
  const administratorCredentials = JSON.parse(credentialInput);
  for (const fieldName of ['email', 'name', 'username', 'password']) {
    const fieldValue = administratorCredentials[fieldName];
    if (typeof fieldValue !== 'string' || !fieldValue.trim() || fieldValue.startsWith('CHANGE_ME_')) {
      throw new Error(`관리자 설정의 ${fieldName} 항목을 실제 값으로 바꿔 주세요.`);
    }
  }
  if (administratorCredentials.password.length < 8) {
    throw new Error('관리자 password는 8자 이상이어야 합니다.');
  }
  await connectDatabase();
  const existingAdministrator = await User.findOne({ email: administratorCredentials.email });
  if (existingAdministrator) {
    if (existingAdministrator.role !== 'ADMIN') {
      throw new Error('기존 계정이 administrator가 아닙니다. 수동 확인이 필요합니다.');
    }
    console.log('기존 administrator를 유지합니다.');
    await mongoose.disconnect();
    return;
  }
  if ((await User.countDocuments({})) !== 0) {
    throw new Error('기존 사용자가 있어 최초 administrator 생성을 중단합니다.');
  }
  const registrationResult = await registerUser(
    {
      ...administratorCredentials,
      confirm_password: administratorCredentials.password,
    },
    { emailVerified: true },
  );
  if (registrationResult.status !== 200) {
    throw new Error('공식 registerUser가 계정 생성을 거부했습니다.');
  }
  console.log('최초 administrator 생성 완료. Password는 local 자격 증명 파일에서 확인해 주세요.');
  await mongoose.disconnect();
}

/** CLI에서 생성한 background handle을 남기지 않고 종료합니다. */
function finishProvisioning() {
  process.exit(0);
}

/** 자격 증명을 출력하지 않고 CLI 실패를 보고합니다. */
async function reportProvisioningFailure(error) {
  console.error(error.message);
  await mongoose.disconnect();
  process.exit(1);
}

provisionAdministrator().then(finishProvisioning).catch(reportProvisioningFailure);
